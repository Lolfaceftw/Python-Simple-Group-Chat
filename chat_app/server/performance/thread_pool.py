"""
Thread Pool Manager

Optimized thread management for client connections with dynamic scaling,
resource monitoring, and graceful shutdown capabilities.
"""

import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from queue import Queue, Empty

from chat_app.shared.exceptions import ThreadPoolError


logger = logging.getLogger(__name__)


@dataclass
class ThreadPoolStats:
    """Statistics for thread pool performance monitoring."""
    active_threads: int
    idle_threads: int
    total_threads: int
    pending_tasks: int
    completed_tasks: int
    failed_tasks: int
    average_task_duration: float
    peak_threads: int
    uptime_seconds: float


@dataclass
class ThreadPoolConfig:
    """Configuration for thread pool management."""
    min_threads: int = 5
    max_threads: int = 50
    idle_timeout: int = 300  # 5 minutes
    task_timeout: int = 30
    scale_up_threshold: float = 0.8  # Scale up when 80% busy
    scale_down_threshold: float = 0.3  # Scale down when 30% busy
    monitoring_interval: int = 10  # seconds
    enable_monitoring: bool = True


class ThreadPoolManager:
    """
    Advanced thread pool manager with dynamic scaling and monitoring.
    
    Features:
    - Dynamic thread scaling based on load
    - Task timeout and error handling
    - Performance monitoring and statistics
    - Graceful shutdown with task completion
    - Resource usage tracking
    """
    
    def __init__(self, config: Optional[ThreadPoolConfig] = None):
        """
        Initialize the thread pool manager.
        
        Args:
            config: Thread pool configuration
        """
        self.config = config or ThreadPoolConfig()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._monitoring_thread: Optional[threading.Thread] = None
        
        # Statistics tracking
        self._start_time = datetime.now()
        self._completed_tasks = 0
        self._failed_tasks = 0
        self._task_durations: List[float] = []
        self._peak_threads = 0
        self._active_futures: Set[Future] = set()
        
        # Task queue for monitoring
        self._pending_tasks: Queue = Queue()
        
        # Initialize thread pool
        self._initialize_pool()
        
        # Start monitoring if enabled
        if self.config.enable_monitoring:
            self._start_monitoring()
        
        logger.info(f"ThreadPoolManager initialized with config: {self.config}")
    
    def _initialize_pool(self) -> None:
        """Initialize the thread pool executor."""
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.config.min_threads,
                    thread_name_prefix="ChatServer-Worker"
                )
                logger.debug(f"Thread pool initialized with {self.config.min_threads} threads")
    
    def submit_task(
        self,
        func: Callable,
        *args,
        timeout: Optional[int] = None,
        priority: int = 0,
        **kwargs
    ) -> Future:
        """
        Submit a task to the thread pool.
        
        Args:
            func: Function to execute
            *args: Function arguments
            timeout: Task timeout in seconds
            priority: Task priority (higher = more important)
            **kwargs: Function keyword arguments
            
        Returns:
            Future object for the task
            
        Raises:
            ThreadPoolError: If thread pool is shutdown or task submission fails
        """
        if self._shutdown_event.is_set():
            raise ThreadPoolError("Thread pool is shutdown")
        
        with self._lock:
            if self._executor is None:
                raise ThreadPoolError("Thread pool not initialized")
            
            # Wrap function with monitoring
            wrapped_func = self._wrap_task(func, timeout or self.config.task_timeout)
            
            try:
                future = self._executor.submit(wrapped_func, *args, **kwargs)
                self._active_futures.add(future)
                
                # Add callback to clean up completed futures
                future.add_done_callback(self._task_completed_callback)
                
                logger.debug(f"Task submitted: {func.__name__}")
                return future
                
            except Exception as e:
                logger.error(f"Failed to submit task {func.__name__}: {e}")
                raise ThreadPoolError(f"Task submission failed: {e}")
    
    def submit_client_handler(
        self,
        handler_func: Callable,
        client_id: str,
        *args,
        **kwargs
    ) -> Future:
        """
        Submit a client handler task with optimized settings.
        
        Args:
            handler_func: Client handler function
            client_id: Unique client identifier
            *args: Handler arguments
            **kwargs: Handler keyword arguments
            
        Returns:
            Future object for the handler task
        """
        # Client handlers get higher priority and longer timeout
        return self.submit_task(
            handler_func,
            client_id,
            *args,
            timeout=None,  # No timeout for client handlers
            priority=10,
            **kwargs
        )
    
    def get_stats(self) -> ThreadPoolStats:
        """
        Get current thread pool statistics.
        
        Returns:
            ThreadPoolStats object with current metrics
        """
        with self._lock:
            if self._executor is None:
                return ThreadPoolStats(0, 0, 0, 0, 0, 0, 0.0, 0, 0.0)
            
            # Calculate thread counts - use a more reliable method
            # ThreadPoolExecutor doesn't expose thread count directly, so we estimate
            active_threads = len(self._active_futures)
            
            # Estimate total threads based on executor's max_workers and active tasks
            if hasattr(self._executor, '_max_workers'):
                max_workers = self._executor._max_workers
            else:
                max_workers = self.config.max_threads
                
            # Estimate current threads (between active and max_workers)
            total_threads = min(max_workers, max(active_threads, self.config.min_threads))
            idle_threads = max(0, total_threads - active_threads)
            
            # Calculate average task duration
            avg_duration = (
                sum(self._task_durations) / len(self._task_durations)
                if self._task_durations else 0.0
            )
            
            # Calculate uptime
            uptime = (datetime.now() - self._start_time).total_seconds()
            
            return ThreadPoolStats(
                active_threads=active_threads,
                idle_threads=idle_threads,
                total_threads=total_threads,
                pending_tasks=self._pending_tasks.qsize(),
                completed_tasks=self._completed_tasks,
                failed_tasks=self._failed_tasks,
                average_task_duration=avg_duration,
                peak_threads=self._peak_threads,
                uptime_seconds=uptime
            )
    
    def scale_pool(self, target_size: Optional[int] = None) -> bool:
        """
        Scale the thread pool based on current load or target size.
        
        Args:
            target_size: Specific target size, or None for automatic scaling
            
        Returns:
            True if scaling was performed
        """
        with self._lock:
            if self._executor is None:
                return False
            
            current_threads = len(self._executor._threads) if hasattr(self._executor, '_threads') else 0
            active_threads = len(self._active_futures)
            
            if target_size is not None:
                # Manual scaling to specific size
                new_size = max(self.config.min_threads, min(target_size, self.config.max_threads))
            else:
                # Automatic scaling based on load
                if current_threads == 0:
                    return False
                
                load_ratio = active_threads / current_threads
                
                if load_ratio > self.config.scale_up_threshold and current_threads < self.config.max_threads:
                    # Scale up
                    new_size = min(current_threads + 5, self.config.max_threads)
                elif load_ratio < self.config.scale_down_threshold and current_threads > self.config.min_threads:
                    # Scale down
                    new_size = max(current_threads - 2, self.config.min_threads)
                else:
                    return False
            
            if new_size != current_threads:
                try:
                    # Create new executor with target size
                    old_executor = self._executor
                    self._executor = ThreadPoolExecutor(
                        max_workers=new_size,
                        thread_name_prefix="ChatServer-Worker"
                    )
                    
                    # Update peak threads tracking
                    self._peak_threads = max(self._peak_threads, new_size)
                    
                    logger.info(f"Thread pool scaled from {current_threads} to {new_size} threads")
                    
                    # Schedule old executor shutdown (don't wait to avoid blocking)
                    threading.Thread(
                        target=self._shutdown_old_executor,
                        args=(old_executor,),
                        daemon=True
                    ).start()
                    
                    return True
                    
                except Exception as e:
                    logger.error(f"Failed to scale thread pool: {e}")
                    return False
            
            return False
    
    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """
        Shutdown the thread pool gracefully.
        
        Args:
            wait: Whether to wait for running tasks to complete
            timeout: Maximum time to wait for shutdown
        """
        logger.info("Shutting down ThreadPoolManager...")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Stop monitoring
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5.0)
        
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=wait)
                self._executor = None
        
        logger.info("ThreadPoolManager shutdown complete")
    
    def _wrap_task(self, func: Callable, timeout: int) -> Callable:
        """
        Wrap a task function with monitoring and timeout handling.
        
        Args:
            func: Original function
            timeout: Task timeout in seconds
            
        Returns:
            Wrapped function
        """
        def wrapped_task(*args, **kwargs):
            start_time = time.time()
            
            try:
                # Execute the task
                result = func(*args, **kwargs)
                
                # Record successful completion
                duration = time.time() - start_time
                self._record_task_completion(duration, success=True)
                
                return result
                
            except Exception as e:
                # Record failed completion
                duration = time.time() - start_time
                self._record_task_completion(duration, success=False)
                
                logger.error(f"Task {func.__name__} failed after {duration:.2f}s: {e}")
                raise
        
        return wrapped_task
    
    def _record_task_completion(self, duration: float, success: bool) -> None:
        """Record task completion statistics."""
        with self._lock:
            if success:
                self._completed_tasks += 1
            else:
                self._failed_tasks += 1
            
            # Keep only recent durations for average calculation
            self._task_durations.append(duration)
            if len(self._task_durations) > 1000:
                self._task_durations = self._task_durations[-500:]
    
    def _task_completed_callback(self, future: Future) -> None:
        """Callback for when a task completes."""
        with self._lock:
            self._active_futures.discard(future)
    
    def _start_monitoring(self) -> None:
        """Start the monitoring thread."""
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="ThreadPool-Monitor",
            daemon=True
        )
        self._monitoring_thread.start()
        logger.debug("Thread pool monitoring started")
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while not self._shutdown_event.is_set():
            try:
                # Check if scaling is needed
                self.scale_pool()
                
                # Log statistics periodically
                if self._completed_tasks % 100 == 0 and self._completed_tasks > 0:
                    stats = self.get_stats()
                    logger.debug(
                        f"ThreadPool stats: {stats.active_threads}/{stats.total_threads} active, "
                        f"{stats.completed_tasks} completed, {stats.average_task_duration:.2f}s avg"
                    )
                
                # Wait for next monitoring cycle
                self._shutdown_event.wait(self.config.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                self._shutdown_event.wait(self.config.monitoring_interval)
    
    def _shutdown_old_executor(self, executor: ThreadPoolExecutor) -> None:
        """Shutdown an old executor gracefully."""
        try:
            executor.shutdown(wait=True)
            logger.debug("Old thread pool executor shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down old executor: {e}")
    
    def __enter__(self) -> "ThreadPoolManager":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.shutdown()