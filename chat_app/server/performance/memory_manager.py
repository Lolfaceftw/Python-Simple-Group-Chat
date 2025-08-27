"""
Memory Management System

Optimized memory management for message history, client data, and resource usage
with configurable limits and automatic cleanup.
"""

import gc
import threading
import time
import logging
import os

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
from collections import deque, defaultdict
from typing import Dict, List, Optional, Any, Callable, NamedTuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from chat_app.shared.models import Message, MessageType
from chat_app.shared.exceptions import MemoryManagerError


logger = logging.getLogger(__name__)


class MemoryPressureLevel(Enum):
    """Memory pressure levels for adaptive management."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MemoryStats:
    """Memory usage statistics."""
    total_memory_mb: float
    used_memory_mb: float
    available_memory_mb: float
    memory_percent: float
    message_history_size: int
    message_history_memory_mb: float
    client_data_memory_mb: float
    cache_memory_mb: float
    pressure_level: MemoryPressureLevel


@dataclass
class MemoryConfig:
    """Configuration for memory management."""
    max_message_history: int = 1000
    max_memory_usage_percent: float = 80.0
    cleanup_threshold_percent: float = 70.0
    critical_threshold_percent: float = 90.0
    monitoring_interval: int = 30  # seconds
    enable_auto_cleanup: bool = True
    enable_compression: bool = True
    max_client_history_per_user: int = 100
    cache_ttl_seconds: int = 3600  # 1 hour


class MessageHistoryManager:
    """
    Manages message history with memory-efficient storage and automatic cleanup.
    
    Features:
    - Configurable message history limits
    - Memory-efficient storage with compression
    - Automatic cleanup based on age and memory pressure
    - Per-client message history tracking
    - Statistics and monitoring
    """
    
    def __init__(self, config: Optional[MemoryConfig] = None):
        """
        Initialize the message history manager.
        
        Args:
            config: Memory management configuration
        """
        self.config = config or MemoryConfig()
        
        # Thread-safe data structures
        self._lock = threading.RLock()
        self._global_history: deque = deque(maxlen=self.config.max_message_history)
        self._client_histories: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.config.max_client_history_per_user)
        )
        
        # Message indexing for efficient retrieval
        self._message_index: Dict[str, List[Message]] = defaultdict(list)
        self._timestamp_index: Dict[datetime, List[Message]] = defaultdict(list)
        
        # Statistics
        self.total_messages_stored = 0
        self.total_messages_cleaned = 0
        self.last_cleanup_time = datetime.now()
        
        logger.info(f"MessageHistoryManager initialized with max_history={self.config.max_message_history}")
    
    def add_message(self, message: Message, client_id: Optional[str] = None) -> None:
        """
        Add a message to history with memory management.
        
        Args:
            message: Message to add
            client_id: Optional client ID for per-client history
        """
        with self._lock:
            # Add to global history
            if message.message_type == MessageType.CHAT:
                self._global_history.append(message)
                self.total_messages_stored += 1
                
                # Update indexes
                self._message_index[message.sender].append(message)
                self._timestamp_index[message.timestamp].append(message)
                
                # Add to client-specific history if provided
                if client_id:
                    self._client_histories[client_id].append(message)
                
                logger.debug(f"Message added to history: {message.content[:50]}...")
    
    def get_recent_messages(self, count: int = 20) -> List[Message]:
        """
        Get recent messages from global history.
        
        Args:
            count: Number of recent messages to retrieve
            
        Returns:
            List of recent messages
        """
        with self._lock:
            return list(self._global_history)[-count:]
    
    def get_client_history(self, client_id: str, count: int = 50) -> List[Message]:
        """
        Get message history for a specific client.
        
        Args:
            client_id: Client identifier
            count: Number of messages to retrieve
            
        Returns:
            List of messages for the client
        """
        with self._lock:
            if client_id in self._client_histories:
                return list(self._client_histories[client_id])[-count:]
            return []
    
    def get_messages_by_sender(self, sender: str, count: int = 50) -> List[Message]:
        """
        Get messages by a specific sender.
        
        Args:
            sender: Sender username
            count: Maximum number of messages to retrieve
            
        Returns:
            List of messages from the sender
        """
        with self._lock:
            if sender in self._message_index:
                return self._message_index[sender][-count:]
            return []
    
    def get_messages_in_timerange(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Message]:
        """
        Get messages within a specific time range.
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            
        Returns:
            List of messages in the time range
        """
        with self._lock:
            messages = []
            for timestamp, msgs in self._timestamp_index.items():
                if start_time <= timestamp <= end_time:
                    messages.extend(msgs)
            
            # Sort by timestamp
            messages.sort(key=lambda m: m.timestamp)
            return messages
    
    def cleanup_old_messages(self, max_age_hours: int = 24) -> int:
        """
        Clean up old messages based on age.
        
        Args:
            max_age_hours: Maximum age of messages to keep
            
        Returns:
            Number of messages cleaned up
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cutoff_timestamp = cutoff_time.timestamp()
        cleaned_count = 0
        
        with self._lock:
            # Clean global history
            original_size = len(self._global_history)
            self._global_history = deque(
                (msg for msg in self._global_history if msg.timestamp > cutoff_timestamp),
                maxlen=self.config.max_message_history
            )
            cleaned_count += original_size - len(self._global_history)
            
            # Clean client histories
            for client_id in list(self._client_histories.keys()):
                client_history = self._client_histories[client_id]
                original_client_size = len(client_history)
                
                # Filter out old messages
                filtered_messages = [
                    msg for msg in client_history 
                    if msg.timestamp > cutoff_time
                ]
                
                if filtered_messages:
                    self._client_histories[client_id] = deque(
                        filtered_messages,
                        maxlen=self.config.max_client_history_per_user
                    )
                else:
                    # Remove empty client history
                    del self._client_histories[client_id]
                
                cleaned_count += original_client_size - len(filtered_messages)
            
            # Clean indexes
            self._cleanup_indexes(cutoff_time)
            
            self.total_messages_cleaned += cleaned_count
            self.last_cleanup_time = datetime.now()
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old messages (older than {max_age_hours}h)")
        
        return cleaned_count
    
    def get_memory_usage(self) -> Dict[str, float]:
        """
        Get memory usage statistics for message history.
        
        Returns:
            Dictionary with memory usage information in MB
        """
        with self._lock:
            # Estimate memory usage (rough calculation)
            global_history_size = sum(
                len(msg.content) + len(msg.sender) + 100  # rough overhead
                for msg in self._global_history
            )
            
            client_histories_size = sum(
                sum(len(msg.content) + len(msg.sender) + 100 for msg in history)
                for history in self._client_histories.values()
            )
            
            index_size = sum(
                sum(len(msg.content) + len(msg.sender) + 100 for msg in msgs)
                for msgs in self._message_index.values()
            )
            
            return {
                'global_history_mb': global_history_size / (1024 * 1024),
                'client_histories_mb': client_histories_size / (1024 * 1024),
                'indexes_mb': index_size / (1024 * 1024),
                'total_mb': (global_history_size + client_histories_size + index_size) / (1024 * 1024)
            }
    
    def clear_all_history(self) -> int:
        """
        Clear all message history.
        
        Returns:
            Number of messages cleared
        """
        with self._lock:
            total_cleared = len(self._global_history)
            
            # Clear all data structures
            self._global_history.clear()
            
            for client_history in self._client_histories.values():
                total_cleared += len(client_history)
            self._client_histories.clear()
            
            self._message_index.clear()
            self._timestamp_index.clear()
            
            logger.info(f"All message history cleared: {total_cleared} messages")
            return total_cleared
    
    def _cleanup_indexes(self, cutoff_time: datetime) -> None:
        """Clean up message indexes based on cutoff time."""
        # Clean message index
        for sender in list(self._message_index.keys()):
            messages = self._message_index[sender]
            filtered_messages = [msg for msg in messages if msg.timestamp > cutoff_time]
            
            if filtered_messages:
                self._message_index[sender] = filtered_messages
            else:
                del self._message_index[sender]
        
        # Clean timestamp index
        for timestamp in list(self._timestamp_index.keys()):
            if timestamp <= cutoff_time:
                del self._timestamp_index[timestamp]


class MemoryManager:
    """
    Comprehensive memory management system for the chat server.
    
    Features:
    - System memory monitoring
    - Automatic cleanup based on memory pressure
    - Configurable memory limits and thresholds
    - Memory usage statistics and reporting
    - Integration with message history management
    """
    
    def __init__(self, config: Optional[MemoryConfig] = None):
        """
        Initialize the memory manager.
        
        Args:
            config: Memory management configuration
        """
        self.config = config or MemoryConfig()
        
        # Components
        self.history_manager = MessageHistoryManager(config)
        
        # Monitoring
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._monitoring_thread: Optional[threading.Thread] = None
        
        # Cache for temporary data
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        
        # Statistics
        self.cleanup_runs = 0
        self.last_memory_check = datetime.now()
        self.peak_memory_usage = 0.0
        
        # Start monitoring if enabled
        if self.config.enable_auto_cleanup:
            self._start_monitoring()
        
        logger.info(f"MemoryManager initialized with auto_cleanup={'enabled' if self.config.enable_auto_cleanup else 'disabled'}")
    
    def get_memory_stats(self) -> MemoryStats:
        """
        Get comprehensive memory statistics.
        
        Returns:
            MemoryStats object with current memory information
        """
        try:
            if HAS_PSUTIL:
                # Get system memory info
                memory = psutil.virtual_memory()
                total_memory_mb = memory.total / (1024 * 1024)
                used_memory_mb = memory.used / (1024 * 1024)
                available_memory_mb = memory.available / (1024 * 1024)
                memory_percent = memory.percent
            else:
                # Fallback when psutil is not available
                total_memory_mb = 8192.0  # Assume 8GB
                used_memory_mb = 4096.0   # Assume 4GB used
                available_memory_mb = 4096.0
                memory_percent = 50.0
            
            # Get message history memory usage
            history_usage = self.history_manager.get_memory_usage()
            
            # Calculate cache memory usage
            cache_memory = sum(
                len(str(value)) for value in self._cache.values()
            ) / (1024 * 1024)  # Convert to MB
            
            # Determine pressure level
            pressure_level = self._calculate_pressure_level(memory_percent)
            
            return MemoryStats(
                total_memory_mb=total_memory_mb,
                used_memory_mb=used_memory_mb,
                available_memory_mb=available_memory_mb,
                memory_percent=memory_percent,
                message_history_size=len(self.history_manager._global_history),
                message_history_memory_mb=history_usage['total_mb'],
                client_data_memory_mb=0.0,  # Placeholder for client data
                cache_memory_mb=cache_memory,
                pressure_level=pressure_level
            )
            
        except Exception as e:
            logger.error(f"Error getting memory stats: {e}")
            return MemoryStats(
                total_memory_mb=0.0,
                used_memory_mb=0.0,
                available_memory_mb=0.0,
                memory_percent=0.0,
                message_history_size=0,
                message_history_memory_mb=0.0,
                client_data_memory_mb=0.0,
                cache_memory_mb=0.0,
                pressure_level=MemoryPressureLevel.LOW
            )
    
    def check_memory_pressure(self) -> MemoryPressureLevel:
        """
        Check current memory pressure level.
        
        Returns:
            Current memory pressure level
        """
        stats = self.get_memory_stats()
        return stats.pressure_level
    
    def cleanup_if_needed(self, force: bool = False) -> bool:
        """
        Perform cleanup if memory pressure is high or if forced.
        
        Args:
            force: Force cleanup regardless of memory pressure
            
        Returns:
            True if cleanup was performed
        """
        stats = self.get_memory_stats()
        
        should_cleanup = (
            force or
            stats.memory_percent > self.config.cleanup_threshold_percent or
            stats.pressure_level in [MemoryPressureLevel.HIGH, MemoryPressureLevel.CRITICAL]
        )
        
        if should_cleanup:
            return self._perform_cleanup(stats)
        
        return False
    
    def add_to_cache(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """
        Add an item to the memory cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds (uses config default if None)
        """
        with self._lock:
            self._cache[key] = value
            self._cache_timestamps[key] = datetime.now()
            
            # Clean expired items periodically
            if len(self._cache) % 100 == 0:  # Every 100 additions
                self._cleanup_cache()
    
    def get_from_cache(self, key: str) -> Optional[Any]:
        """
        Get an item from the memory cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                return None
            
            # Check if expired
            timestamp = self._cache_timestamps.get(key)
            if timestamp:
                age = (datetime.now() - timestamp).total_seconds()
                if age > self.config.cache_ttl_seconds:
                    del self._cache[key]
                    del self._cache_timestamps[key]
                    return None
            
            return self._cache[key]
    
    def clear_cache(self) -> int:
        """
        Clear all cached items.
        
        Returns:
            Number of items cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._cache_timestamps.clear()
            logger.info(f"Cache cleared: {count} items removed")
            return count
    
    def shutdown(self) -> None:
        """Shutdown the memory manager and stop monitoring."""
        logger.info("Shutting down MemoryManager...")
        
        self._shutdown_event.set()
        
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5.0)
        
        # Clear all data
        self.clear_cache()
        
        logger.info("MemoryManager shutdown complete")
    
    def _start_monitoring(self) -> None:
        """Start the memory monitoring thread."""
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="Memory-Monitor",
            daemon=True
        )
        self._monitoring_thread.start()
        logger.debug("Memory monitoring started")
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop for memory management."""
        while not self._shutdown_event.is_set():
            try:
                # Check memory pressure and cleanup if needed
                self.cleanup_if_needed()
                
                # Update statistics
                stats = self.get_memory_stats()
                self.peak_memory_usage = max(self.peak_memory_usage, stats.memory_percent)
                self.last_memory_check = datetime.now()
                
                # Log memory stats periodically
                if self.cleanup_runs % 10 == 0:  # Every 10 monitoring cycles
                    logger.debug(
                        f"Memory stats: {stats.memory_percent:.1f}% used, "
                        f"{stats.message_history_size} messages in history, "
                        f"pressure: {stats.pressure_level.value}"
                    )
                
                # Wait for next monitoring cycle
                self._shutdown_event.wait(self.config.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")
                self._shutdown_event.wait(self.config.monitoring_interval)
    
    def _perform_cleanup(self, stats: MemoryStats) -> bool:
        """
        Perform memory cleanup based on current statistics.
        
        Args:
            stats: Current memory statistics
            
        Returns:
            True if cleanup was performed
        """
        logger.info(f"Performing memory cleanup (pressure: {stats.pressure_level.value}, usage: {stats.memory_percent:.1f}%)")
        
        cleanup_performed = False
        
        # Clean message history based on pressure level
        if stats.pressure_level == MemoryPressureLevel.CRITICAL:
            # Aggressive cleanup
            cleaned = self.history_manager.cleanup_old_messages(max_age_hours=6)
            cleanup_performed = cleaned > 0
        elif stats.pressure_level == MemoryPressureLevel.HIGH:
            # Moderate cleanup
            cleaned = self.history_manager.cleanup_old_messages(max_age_hours=12)
            cleanup_performed = cleaned > 0
        else:
            # Light cleanup
            cleaned = self.history_manager.cleanup_old_messages(max_age_hours=24)
            cleanup_performed = cleaned > 0
        
        # Clean cache
        cache_cleaned = self._cleanup_cache()
        cleanup_performed = cleanup_performed or cache_cleaned > 0
        
        # Force garbage collection
        if cleanup_performed:
            gc.collect()
        
        self.cleanup_runs += 1
        
        logger.info(f"Memory cleanup complete (messages: {cleaned}, cache: {cache_cleaned})")
        return cleanup_performed
    
    def _cleanup_cache(self) -> int:
        """
        Clean up expired cache items.
        
        Returns:
            Number of items cleaned up
        """
        with self._lock:
            current_time = datetime.now()
            expired_keys = []
            
            for key, timestamp in self._cache_timestamps.items():
                age = (current_time - timestamp).total_seconds()
                if age > self.config.cache_ttl_seconds:
                    expired_keys.append(key)
            
            # Remove expired items
            for key in expired_keys:
                del self._cache[key]
                del self._cache_timestamps[key]
            
            return len(expired_keys)
    
    def _calculate_pressure_level(self, memory_percent: float) -> MemoryPressureLevel:
        """
        Calculate memory pressure level based on usage percentage.
        
        Args:
            memory_percent: Memory usage percentage
            
        Returns:
            Appropriate memory pressure level
        """
        if memory_percent >= self.config.critical_threshold_percent:
            return MemoryPressureLevel.CRITICAL
        elif memory_percent >= self.config.max_memory_usage_percent:
            return MemoryPressureLevel.HIGH
        elif memory_percent >= self.config.cleanup_threshold_percent:
            return MemoryPressureLevel.MEDIUM
        else:
            return MemoryPressureLevel.LOW