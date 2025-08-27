"""
High-Performance Message Queue

Optimized message queuing system with priority handling, batching,
and memory-efficient delivery for the chat server.
"""

import threading
import time
import logging
from collections import deque
from queue import PriorityQueue, Empty, Full
from typing import Dict, List, Optional, Callable, Any, Tuple, NamedTuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum

from chat_app.shared.models import Message, MessageType
from chat_app.shared.exceptions import MessageQueueError


logger = logging.getLogger(__name__)


class MessagePriority(IntEnum):
    """Message priority levels (lower number = higher priority)."""
    CRITICAL = 0    # System critical messages
    HIGH = 1        # Server notifications, user joins/leaves
    NORMAL = 2      # Regular chat messages
    LOW = 3         # Background updates, statistics


@dataclass
class QueuedMessage:
    """Message wrapper for queue processing."""
    message: Message
    priority: MessagePriority
    target_clients: List[str]
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3
    
    def __lt__(self, other: 'QueuedMessage') -> bool:
        """Priority comparison for queue ordering."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp


@dataclass
class MessageBatch:
    """Batch of messages for efficient delivery."""
    messages: List[QueuedMessage]
    target_client: str
    created_at: datetime = field(default_factory=datetime.now)
    
    def size(self) -> int:
        """Get total size of messages in batch."""
        return sum(len(msg.message.content) for msg in self.messages)


@dataclass
class QueueStats:
    """Statistics for message queue performance."""
    total_queued: int = 0
    total_processed: int = 0
    total_failed: int = 0
    total_retries: int = 0
    current_queue_size: int = 0
    average_processing_time: float = 0.0
    peak_queue_size: int = 0
    batches_created: int = 0
    batches_processed: int = 0


class MessageQueue:
    """
    High-performance message queue with priority handling and batching.
    
    Features:
    - Priority-based message ordering
    - Message batching for efficiency
    - Automatic retry mechanism
    - Memory usage monitoring
    - Performance statistics
    - Configurable delivery strategies
    """
    
    def __init__(
        self,
        max_queue_size: int = 10000,
        batch_size: int = 10,
        batch_timeout: float = 0.1,  # 100ms
        enable_batching: bool = True,
        enable_compression: bool = False,
        worker_threads: int = 2
    ):
        """
        Initialize the message queue.
        
        Args:
            max_queue_size: Maximum number of messages in queue
            batch_size: Maximum messages per batch
            batch_timeout: Maximum time to wait for batch completion
            enable_batching: Whether to enable message batching
            enable_compression: Whether to compress large messages
            worker_threads: Number of worker threads for processing
        """
        self.max_queue_size = max_queue_size
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.enable_batching = enable_batching
        self.enable_compression = enable_compression
        self.worker_threads = worker_threads
        
        # Thread-safe queue and data structures
        self._queue: PriorityQueue = PriorityQueue(maxsize=max_queue_size)
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._worker_threads: List[threading.Thread] = []
        
        # Batching support
        self._pending_batches: Dict[str, MessageBatch] = {}
        self._batch_timers: Dict[str, threading.Timer] = {}
        
        # Message delivery callback
        self._delivery_callback: Optional[Callable[[List[QueuedMessage]], bool]] = None
        
        # Statistics
        self._stats = QueueStats()
        self._processing_times: deque = deque(maxlen=1000)
        
        # Start worker threads
        self._start_workers()
        
        logger.info(
            f"MessageQueue initialized: max_size={max_queue_size}, "
            f"batch_size={batch_size}, workers={worker_threads}, "
            f"batching={'enabled' if enable_batching else 'disabled'}"
        )
    
    def set_delivery_callback(self, callback: Callable[[List[QueuedMessage]], bool]) -> None:
        """
        Set the callback function for message delivery.
        
        Args:
            callback: Function that takes a list of QueuedMessage and returns success bool
        """
        self._delivery_callback = callback
        logger.debug("Message delivery callback registered")
    
    def enqueue_message(
        self,
        message: Message,
        target_clients: List[str],
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> bool:
        """
        Add a message to the queue for delivery.
        
        Args:
            message: Message to queue
            target_clients: List of client IDs to deliver to
            priority: Message priority level
            
        Returns:
            True if message was queued successfully
            
        Raises:
            MessageQueueError: If queue is full or shutdown
        """
        if self._shutdown_event.is_set():
            raise MessageQueueError("Message queue is shutdown")
        
        if not target_clients:
            logger.warning("No target clients specified for message")
            return False
        
        try:
            queued_msg = QueuedMessage(
                message=message,
                priority=priority,
                target_clients=target_clients.copy()
            )
            
            # Try to add to queue (non-blocking)
            self._queue.put_nowait(queued_msg)
            
            with self._lock:
                self._stats.total_queued += 1
                self._stats.current_queue_size = self._queue.qsize()
                self._stats.peak_queue_size = max(
                    self._stats.peak_queue_size,
                    self._stats.current_queue_size
                )
            
            logger.debug(
                f"Message queued: {message.message_type} to {len(target_clients)} clients "
                f"(priority: {priority.name}, queue size: {self._queue.qsize()})"
            )
            
            return True
            
        except Full:
            logger.error(f"Message queue is full (size: {self._queue.qsize()})")
            raise MessageQueueError("Message queue is full")
        except Exception as e:
            logger.error(f"Failed to enqueue message: {e}")
            return False
    
    def enqueue_broadcast(
        self,
        message: Message,
        all_clients: List[str],
        exclude_clients: Optional[List[str]] = None,
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> bool:
        """
        Queue a message for broadcast to multiple clients.
        
        Args:
            message: Message to broadcast
            all_clients: List of all client IDs
            exclude_clients: Optional list of clients to exclude
            priority: Message priority level
            
        Returns:
            True if message was queued successfully
        """
        exclude_set = set(exclude_clients or [])
        target_clients = [client for client in all_clients if client not in exclude_set]
        
        return self.enqueue_message(message, target_clients, priority)
    
    def get_stats(self) -> QueueStats:
        """
        Get current queue statistics.
        
        Returns:
            QueueStats object with current metrics
        """
        with self._lock:
            stats = QueueStats(
                total_queued=self._stats.total_queued,
                total_processed=self._stats.total_processed,
                total_failed=self._stats.total_failed,
                total_retries=self._stats.total_retries,
                current_queue_size=self._queue.qsize(),
                average_processing_time=self._calculate_average_processing_time(),
                peak_queue_size=self._stats.peak_queue_size,
                batches_created=self._stats.batches_created,
                batches_processed=self._stats.batches_processed
            )
            return stats
    
    def clear_queue(self) -> int:
        """
        Clear all pending messages from the queue.
        
        Returns:
            Number of messages that were cleared
        """
        count = 0
        try:
            while True:
                self._queue.get_nowait()
                count += 1
        except Empty:
            pass
        
        with self._lock:
            self._stats.current_queue_size = 0
            self._pending_batches.clear()
            
            # Cancel all batch timers
            for timer in self._batch_timers.values():
                timer.cancel()
            self._batch_timers.clear()
        
        logger.info(f"Message queue cleared: {count} messages removed")
        return count
    
    def shutdown(self, timeout: float = 5.0) -> None:
        """
        Shutdown the message queue and worker threads.
        
        Args:
            timeout: Maximum time to wait for workers to finish
        """
        logger.info("Shutting down MessageQueue...")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel batch timers
        with self._lock:
            for timer in self._batch_timers.values():
                timer.cancel()
            self._batch_timers.clear()
        
        # Wait for worker threads to finish
        for worker in self._worker_threads:
            worker.join(timeout=timeout)
            if worker.is_alive():
                logger.warning(f"Worker thread {worker.name} did not shutdown gracefully")
        
        logger.info("MessageQueue shutdown complete")
    
    def _start_workers(self) -> None:
        """Start worker threads for message processing."""
        for i in range(self.worker_threads):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"MessageQueue-Worker-{i}",
                daemon=True
            )
            worker.start()
            self._worker_threads.append(worker)
        
        logger.debug(f"Started {self.worker_threads} message queue workers")
    
    def _worker_loop(self) -> None:
        """Main worker loop for processing messages."""
        while not self._shutdown_event.is_set():
            try:
                # Get message from queue with timeout
                try:
                    queued_msg = self._queue.get(timeout=1.0)
                except Empty:
                    continue
                
                # Process the message
                start_time = time.time()
                success = self._process_message(queued_msg)
                processing_time = time.time() - start_time
                
                # Update statistics
                with self._lock:
                    self._processing_times.append(processing_time)
                    self._stats.current_queue_size = self._queue.qsize()
                    
                    if success:
                        self._stats.total_processed += 1
                    else:
                        self._stats.total_failed += 1
                
                # Mark task as done
                self._queue.task_done()
                
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(0.1)  # Brief pause on error
    
    def _process_message(self, queued_msg: QueuedMessage) -> bool:
        """
        Process a single queued message.
        
        Args:
            queued_msg: Message to process
            
        Returns:
            True if processing was successful
        """
        if self.enable_batching:
            return self._process_with_batching(queued_msg)
        else:
            return self._process_immediately(queued_msg)
    
    def _process_with_batching(self, queued_msg: QueuedMessage) -> bool:
        """
        Process message with batching optimization.
        
        Args:
            queued_msg: Message to process
            
        Returns:
            True if processing was successful
        """
        success_count = 0
        total_clients = len(queued_msg.target_clients)
        
        for client_id in queued_msg.target_clients:
            try:
                # Add to pending batch for this client
                if client_id not in self._pending_batches:
                    self._pending_batches[client_id] = MessageBatch(
                        messages=[],
                        target_client=client_id
                    )
                
                batch = self._pending_batches[client_id]
                batch.messages.append(queued_msg)
                
                # Check if batch is ready for delivery
                if (len(batch.messages) >= self.batch_size or
                    queued_msg.priority <= MessagePriority.HIGH):
                    
                    # Deliver batch immediately
                    if self._deliver_batch(batch):
                        success_count += 1
                    
                    # Remove from pending
                    del self._pending_batches[client_id]
                    
                    # Cancel timer if exists
                    if client_id in self._batch_timers:
                        self._batch_timers[client_id].cancel()
                        del self._batch_timers[client_id]
                
                else:
                    # Set timer for batch delivery if not already set
                    if client_id not in self._batch_timers:
                        timer = threading.Timer(
                            self.batch_timeout,
                            self._deliver_batch_timeout,
                            args=(client_id,)
                        )
                        timer.start()
                        self._batch_timers[client_id] = timer
                    
                    success_count += 1  # Consider queued for batch as success
                
            except Exception as e:
                logger.error(f"Error processing message for client {client_id}: {e}")
        
        return success_count == total_clients
    
    def _process_immediately(self, queued_msg: QueuedMessage) -> bool:
        """
        Process message immediately without batching.
        
        Args:
            queued_msg: Message to process
            
        Returns:
            True if processing was successful
        """
        if not self._delivery_callback:
            logger.error("No delivery callback registered")
            return False
        
        try:
            # Create individual batches for each client
            success_count = 0
            for client_id in queued_msg.target_clients:
                individual_msg = QueuedMessage(
                    message=queued_msg.message,
                    priority=queued_msg.priority,
                    target_clients=[client_id],
                    timestamp=queued_msg.timestamp,
                    retry_count=queued_msg.retry_count,
                    max_retries=queued_msg.max_retries
                )
                
                if self._delivery_callback([individual_msg]):
                    success_count += 1
                else:
                    # Handle retry logic
                    if queued_msg.retry_count < queued_msg.max_retries:
                        queued_msg.retry_count += 1
                        self._stats.total_retries += 1
                        
                        # Re-queue for retry with lower priority
                        retry_msg = QueuedMessage(
                            message=queued_msg.message,
                            priority=MessagePriority.LOW,
                            target_clients=[client_id],
                            retry_count=queued_msg.retry_count,
                            max_retries=queued_msg.max_retries
                        )
                        
                        try:
                            self._queue.put_nowait(retry_msg)
                        except Full:
                            logger.warning(f"Failed to re-queue retry for client {client_id}")
            
            return success_count == len(queued_msg.target_clients)
            
        except Exception as e:
            logger.error(f"Error in immediate processing: {e}")
            return False
    
    def _deliver_batch(self, batch: MessageBatch) -> bool:
        """
        Deliver a batch of messages to a client.
        
        Args:
            batch: Message batch to deliver
            
        Returns:
            True if delivery was successful
        """
        if not self._delivery_callback:
            logger.error("No delivery callback registered")
            return False
        
        try:
            success = self._delivery_callback(batch.messages)
            
            with self._lock:
                self._stats.batches_processed += 1
                if success:
                    self._stats.total_processed += len(batch.messages)
                else:
                    self._stats.total_failed += len(batch.messages)
            
            logger.debug(
                f"Batch delivered to {batch.target_client}: "
                f"{len(batch.messages)} messages, success={success}"
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Error delivering batch to {batch.target_client}: {e}")
            return False
    
    def _deliver_batch_timeout(self, client_id: str) -> None:
        """
        Handle batch delivery timeout.
        
        Args:
            client_id: Client ID for the batch
        """
        with self._lock:
            if client_id in self._pending_batches:
                batch = self._pending_batches[client_id]
                
                # Deliver the batch
                self._deliver_batch(batch)
                
                # Clean up
                del self._pending_batches[client_id]
                if client_id in self._batch_timers:
                    del self._batch_timers[client_id]
                
                self._stats.batches_created += 1
    
    def _calculate_average_processing_time(self) -> float:
        """Calculate average message processing time."""
        if not self._processing_times:
            return 0.0
        
        return sum(self._processing_times) / len(self._processing_times)
    
    def __enter__(self) -> "MessageQueue":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.shutdown()