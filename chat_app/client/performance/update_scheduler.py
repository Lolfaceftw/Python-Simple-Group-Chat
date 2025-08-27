"""
Update Scheduler

Intelligent scheduling system for UI updates and network operations
to optimize client performance and responsiveness.
"""

import threading
import time
import logging
from collections import deque, defaultdict
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from queue import PriorityQueue, Empty

from chat_app.shared.exceptions import SchedulerError


logger = logging.getLogger(__name__)


class UpdatePriority(IntEnum):
    """Priority levels for scheduled updates."""
    CRITICAL = 0    # System critical updates
    HIGH = 1        # User input, real-time messages
    NORMAL = 2      # Regular UI updates
    LOW = 3         # Background tasks, statistics
    IDLE = 4        # Cleanup, maintenance tasks


@dataclass
class UpdateConfig:
    """Configuration for the update scheduler."""
    max_queue_size: int = 1000
    worker_threads: int = 2
    enable_adaptive_scheduling: bool = True
    enable_update_coalescing: bool = True
    max_update_frequency_hz: int = 60
    idle_task_interval: int = 5  # seconds
    statistics_interval: int = 10  # seconds


@dataclass
class ScheduledUpdate:
    """Represents a scheduled update task."""
    task_id: str
    callback: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: UpdatePriority = UpdatePriority.NORMAL
    scheduled_time: datetime = field(default_factory=datetime.now)
    max_retries: int = 3
    retry_count: int = 0
    coalesce_key: Optional[str] = None  # For update coalescing
    
    def __lt__(self, other: 'ScheduledUpdate') -> bool:
        """Priority comparison for queue ordering."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.scheduled_time < other.scheduled_time


@dataclass
class SchedulerStats:
    """Statistics for update scheduler performance."""
    total_scheduled: int = 0
    total_executed: int = 0
    total_failed: int = 0
    total_coalesced: int = 0
    total_retries: int = 0
    current_queue_size: int = 0
    average_execution_time: float = 0.0
    peak_queue_size: int = 0
    worker_utilization: float = 0.0


class UpdateScheduler:
    """
    Intelligent update scheduler for optimizing client performance.
    
    Features:
    - Priority-based task scheduling
    - Update coalescing to reduce redundant operations
    - Adaptive scheduling based on system load
    - Worker thread pool for concurrent execution
    - Performance monitoring and statistics
    - Automatic retry mechanism for failed updates
    """
    
    def __init__(self, config: Optional[UpdateConfig] = None):
        """
        Initialize the update scheduler.
        
        Args:
            config: Scheduler configuration
        """
        self.config = config or UpdateConfig()
        
        # Threading and synchronization
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._worker_threads: List[threading.Thread] = []
        
        # Task management
        self._task_queue: PriorityQueue = PriorityQueue(maxsize=self.config.max_queue_size)
        self._active_tasks: Set[str] = set()
        self._coalesce_map: Dict[str, ScheduledUpdate] = {}
        
        # Scheduling control
        self._last_update_time = 0.0
        self._update_interval = 1.0 / self.config.max_update_frequency_hz
        
        # Statistics and monitoring
        self._stats = SchedulerStats()
        self._execution_times: deque = deque(maxlen=100)
        self._worker_busy_count = 0
        
        # Periodic tasks
        self._idle_tasks: List[Callable] = []
        self._last_idle_run = datetime.now()
        self._last_stats_run = datetime.now()
        
        # Start worker threads
        self._start_workers()
        
        logger.info(f"UpdateScheduler initialized with {self.config.worker_threads} workers")
    
    def schedule_update(
        self,
        task_id: str,
        callback: Callable,
        *args,
        priority: UpdatePriority = UpdatePriority.NORMAL,
        delay_seconds: float = 0.0,
        coalesce_key: Optional[str] = None,
        max_retries: int = 3,
        **kwargs
    ) -> bool:
        """
        Schedule an update task for execution.
        
        Args:
            task_id: Unique identifier for the task
            callback: Function to execute
            *args: Function arguments
            priority: Task priority level
            delay_seconds: Delay before execution
            coalesce_key: Key for update coalescing
            max_retries: Maximum retry attempts
            **kwargs: Function keyword arguments
            
        Returns:
            True if task was scheduled successfully
            
        Raises:
            SchedulerError: If scheduler is shutdown or queue is full
        """
        if self._shutdown_event.is_set():
            raise SchedulerError("Scheduler is shutdown")
        
        # Calculate scheduled time
        scheduled_time = datetime.now()
        if delay_seconds > 0:
            scheduled_time += timedelta(seconds=delay_seconds)
        
        # Create scheduled update
        update = ScheduledUpdate(
            task_id=task_id,
            callback=callback,
            args=args,
            kwargs=kwargs,
            priority=priority,
            scheduled_time=scheduled_time,
            max_retries=max_retries,
            coalesce_key=coalesce_key
        )
        
        # Handle update coalescing
        if self.config.enable_update_coalescing and coalesce_key:
            with self._lock:
                if coalesce_key in self._coalesce_map:
                    # Replace existing update with same coalesce key
                    old_update = self._coalesce_map[coalesce_key]
                    self._coalesce_map[coalesce_key] = update
                    self._stats.total_coalesced += 1
                    
                    logger.debug(f"Update coalesced: {coalesce_key}")
                else:
                    self._coalesce_map[coalesce_key] = update
        
        try:
            # Add to queue
            self._task_queue.put_nowait(update)
            
            with self._lock:
                self._stats.total_scheduled += 1
                self._stats.current_queue_size = self._task_queue.qsize()
                self._stats.peak_queue_size = max(
                    self._stats.peak_queue_size,
                    self._stats.current_queue_size
                )
            
            logger.debug(f"Task scheduled: {task_id} (priority: {priority.name})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule task {task_id}: {e}")
            raise SchedulerError(f"Task scheduling failed: {e}")
    
    def schedule_ui_update(
        self,
        update_type: str,
        callback: Callable,
        *args,
        **kwargs
    ) -> bool:
        """
        Schedule a UI update with automatic coalescing.
        
        Args:
            update_type: Type of UI update
            callback: Update callback function
            *args: Callback arguments
            **kwargs: Callback keyword arguments
            
        Returns:
            True if update was scheduled
        """
        return self.schedule_update(
            f"ui_update_{update_type}_{time.time()}",
            callback,
            *args,
            priority=UpdatePriority.HIGH,
            coalesce_key=f"ui_{update_type}",
            **kwargs
        )
    
    def schedule_network_task(
        self,
        task_name: str,
        callback: Callable,
        *args,
        priority: UpdatePriority = UpdatePriority.NORMAL,
        **kwargs
    ) -> bool:
        """
        Schedule a network-related task.
        
        Args:
            task_name: Name of the network task
            callback: Task callback function
            *args: Callback arguments
            priority: Task priority
            **kwargs: Callback keyword arguments
            
        Returns:
            True if task was scheduled
        """
        return self.schedule_update(
            task_id=f"network_{task_name}_{time.time()}",
            callback=callback,
            *args,
            priority=priority,
            **kwargs
        )
    
    def schedule_periodic_task(
        self,
        task_name: str,
        callback: Callable,
        interval_seconds: float,
        *args,
        priority: UpdatePriority = UpdatePriority.LOW,
        **kwargs
    ) -> bool:
        """
        Schedule a periodic task that repeats at regular intervals.
        
        Args:
            task_name: Name of the periodic task
            callback: Task callback function
            interval_seconds: Interval between executions
            *args: Callback arguments
            priority: Task priority
            **kwargs: Callback keyword arguments
            
        Returns:
            True if task was scheduled
        """
        def periodic_wrapper():
            try:
                # Execute the callback
                callback(*args, **kwargs)
                
                # Reschedule for next execution
                self.schedule_update(
                    task_id=f"periodic_{task_name}_{time.time()}",
                    callback=periodic_wrapper,
                    priority=priority,
                    delay_seconds=interval_seconds
                )
            except Exception as e:
                logger.error(f"Periodic task {task_name} failed: {e}")
        
        return self.schedule_update(
            task_id=f"periodic_{task_name}_{time.time()}",
            callback=periodic_wrapper,
            priority=priority
        )
    
    def add_idle_task(self, callback: Callable) -> None:
        """
        Add a task to be executed during idle periods.
        
        Args:
            callback: Function to execute during idle time
        """
        with self._lock:
            self._idle_tasks.append(callback)
            logger.debug(f"Idle task added: {callback.__name__}")
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a scheduled task (if not yet executing).
        
        Args:
            task_id: ID of the task to cancel
            
        Returns:
            True if task was found and cancelled
        """
        # Note: This is a simplified implementation
        # In practice, cancelling tasks from a PriorityQueue is complex
        with self._lock:
            if task_id in self._active_tasks:
                return False  # Task is already executing
            
            # Remove from coalesce map if present
            for key, update in list(self._coalesce_map.items()):
                if update.task_id == task_id:
                    del self._coalesce_map[key]
                    logger.debug(f"Task cancelled: {task_id}")
                    return True
            
            return False
    
    def get_stats(self) -> SchedulerStats:
        """
        Get current scheduler statistics.
        
        Returns:
            SchedulerStats object with current metrics
        """
        with self._lock:
            # Calculate worker utilization
            utilization = 0.0
            if self.config.worker_threads > 0:
                utilization = self._worker_busy_count / self.config.worker_threads
            
            # Calculate average execution time
            avg_execution_time = 0.0
            if self._execution_times:
                avg_execution_time = sum(self._execution_times) / len(self._execution_times)
            
            return SchedulerStats(
                total_scheduled=self._stats.total_scheduled,
                total_executed=self._stats.total_executed,
                total_failed=self._stats.total_failed,
                total_coalesced=self._stats.total_coalesced,
                total_retries=self._stats.total_retries,
                current_queue_size=self._task_queue.qsize(),
                average_execution_time=avg_execution_time,
                peak_queue_size=self._stats.peak_queue_size,
                worker_utilization=utilization
            )
    
    def clear_queue(self) -> int:
        """
        Clear all pending tasks from the queue.
        
        Returns:
            Number of tasks that were cleared
        """
        count = 0
        try:
            while True:
                self._task_queue.get_nowait()
                count += 1
        except Empty:
            pass
        
        with self._lock:
            self._coalesce_map.clear()
            self._stats.current_queue_size = 0
        
        logger.info(f"Task queue cleared: {count} tasks removed")
        return count
    
    def shutdown(self, timeout: float = 5.0) -> None:
        """
        Shutdown the scheduler and worker threads.
        
        Args:
            timeout: Maximum time to wait for workers to finish
        """
        logger.info("Shutting down UpdateScheduler...")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Wait for worker threads to finish
        for worker in self._worker_threads:
            worker.join(timeout=timeout)
            if worker.is_alive():
                logger.warning(f"Worker thread {worker.name} did not shutdown gracefully")
        
        # Clear remaining tasks
        self.clear_queue()
        
        logger.info("UpdateScheduler shutdown complete")
    
    def _start_workers(self) -> None:
        """Start worker threads for task execution."""
        for i in range(self.config.worker_threads):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"UpdateScheduler-Worker-{i}",
                daemon=True
            )
            worker.start()
            self._worker_threads.append(worker)
        
        logger.debug(f"Started {self.config.worker_threads} scheduler workers")
    
    def _worker_loop(self) -> None:
        """Main worker loop for task execution."""
        while not self._shutdown_event.is_set():
            try:
                # Get task from queue with timeout
                try:
                    update = self._task_queue.get(timeout=1.0)
                except Empty:
                    # Check for idle tasks during quiet periods
                    self._run_idle_tasks()
                    continue
                
                # Check if task should be executed now
                if update.scheduled_time > datetime.now():
                    # Re-queue for later execution
                    self._task_queue.put(update)
                    time.sleep(0.1)
                    continue
                
                # Execute the task
                self._execute_task(update)
                
                # Mark task as done
                self._task_queue.task_done()
                
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(0.1)  # Brief pause on error
    
    def _execute_task(self, update: ScheduledUpdate) -> None:
        """
        Execute a scheduled task.
        
        Args:
            update: Task to execute
        """
        with self._lock:
            self._active_tasks.add(update.task_id)
            self._worker_busy_count += 1
        
        start_time = time.time()
        success = False
        
        try:
            # Remove from coalesce map if present
            if update.coalesce_key and update.coalesce_key in self._coalesce_map:
                if self._coalesce_map[update.coalesce_key].task_id == update.task_id:
                    del self._coalesce_map[update.coalesce_key]
            
            # Execute the callback
            result = update.callback(*update.args, **update.kwargs)
            success = True
            
            logger.debug(f"Task executed successfully: {update.task_id}")
            
        except Exception as e:
            logger.error(f"Task execution failed: {update.task_id} - {e}")
            
            # Handle retry logic
            if update.retry_count < update.max_retries:
                update.retry_count += 1
                update.scheduled_time = datetime.now() + timedelta(seconds=2 ** update.retry_count)
                
                try:
                    self._task_queue.put_nowait(update)
                    self._stats.total_retries += 1
                    logger.debug(f"Task queued for retry: {update.task_id} (attempt {update.retry_count})")
                except Exception:
                    logger.error(f"Failed to queue retry for task: {update.task_id}")
        
        finally:
            # Update statistics
            execution_time = time.time() - start_time
            
            with self._lock:
                self._active_tasks.discard(update.task_id)
                self._worker_busy_count = max(0, self._worker_busy_count - 1)
                self._execution_times.append(execution_time)
                
                if success:
                    self._stats.total_executed += 1
                else:
                    self._stats.total_failed += 1
                
                self._stats.current_queue_size = self._task_queue.qsize()
    
    def _run_idle_tasks(self) -> None:
        """Run idle tasks during quiet periods."""
        current_time = datetime.now()
        
        # Check if it's time to run idle tasks
        if (current_time - self._last_idle_run).total_seconds() < self.config.idle_task_interval:
            return
        
        with self._lock:
            idle_tasks = self._idle_tasks.copy()
        
        # Execute idle tasks
        for task in idle_tasks:
            try:
                task()
            except Exception as e:
                logger.error(f"Idle task failed: {e}")
        
        self._last_idle_run = current_time
        
        # Run periodic statistics logging
        if (current_time - self._last_stats_run).total_seconds() >= self.config.statistics_interval:
            self._log_statistics()
            self._last_stats_run = current_time
    
    def _log_statistics(self) -> None:
        """Log scheduler statistics periodically."""
        stats = self.get_stats()
        
        logger.debug(
            f"Scheduler stats: {stats.current_queue_size} queued, "
            f"{stats.total_executed} executed, {stats.worker_utilization:.1%} utilization, "
            f"{stats.average_execution_time:.3f}s avg execution"
        )
    
    def __enter__(self) -> "UpdateScheduler":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.shutdown()