"""
UI Performance Optimizer

Optimizes Rich terminal UI rendering with intelligent update scheduling,
frame rate limiting, and efficient content management.
"""

import threading
import time
import logging
from collections import deque
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from chat_app.shared.exceptions import UIOptimizerError


logger = logging.getLogger(__name__)


class UpdateType(Enum):
    """Types of UI updates for optimization."""
    CHAT_MESSAGE = "chat_message"
    USER_LIST = "user_list"
    STATUS_BAR = "status_bar"
    INPUT_AREA = "input_area"
    FULL_REFRESH = "full_refresh"


@dataclass
class UIConfig:
    """Configuration for UI optimization."""
    target_fps: int = 20
    max_chat_lines: int = 1000
    max_user_list_size: int = 100
    enable_frame_limiting: bool = True
    enable_content_caching: bool = True
    enable_partial_updates: bool = True
    scroll_buffer_size: int = 50
    update_batch_size: int = 10
    update_timeout_ms: int = 50


@dataclass
class RenderStats:
    """Statistics for UI rendering performance."""
    total_renders: int = 0
    total_updates: int = 0
    average_render_time: float = 0.0
    current_fps: float = 0.0
    peak_fps: float = 0.0
    dropped_frames: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    partial_updates: int = 0
    full_refreshes: int = 0


@dataclass
class PendingUpdate:
    """Represents a pending UI update."""
    update_type: UpdateType
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = 1  # Higher number = higher priority


class UIOptimizer:
    """
    UI performance optimizer for Rich terminal interface.
    
    Features:
    - Frame rate limiting and smooth rendering
    - Intelligent update batching and scheduling
    - Content caching to avoid redundant renders
    - Partial updates for better performance
    - Memory-efficient content management
    - Performance monitoring and statistics
    """
    
    def __init__(self, console: Console, config: Optional[UIConfig] = None):
        """
        Initialize the UI optimizer.
        
        Args:
            console: Rich console instance
            config: UI optimization configuration
        """
        self.console = console
        self.config = config or UIConfig()
        
        # Threading and synchronization
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._update_thread: Optional[threading.Thread] = None
        
        # Update management
        self._pending_updates: deque = deque()
        self._last_render_time = 0.0
        self._frame_interval = 1.0 / self.config.target_fps
        
        # Content management
        self._chat_messages: deque = deque(maxlen=self.config.max_chat_lines)
        self._user_list: List[str] = []
        self._status_text = ""
        self._input_text = ""
        
        # Caching
        self._content_cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        
        # Layout components
        self._layout: Optional[Layout] = None
        self._live: Optional[Live] = None
        
        # Statistics
        self._stats = RenderStats()
        self._render_times: deque = deque(maxlen=100)
        self._fps_samples: deque = deque(maxlen=20)
        
        # Start update thread
        self._start_update_thread()
        
        logger.info(f"UIOptimizer initialized with target_fps={self.config.target_fps}")
    
    def initialize_layout(self) -> Layout:
        """
        Initialize the Rich layout for the chat interface.
        
        Returns:
            Configured Layout object
        """
        with self._lock:
            if self._layout is None:
                # Create main layout
                self._layout = Layout()
                
                # Split into main areas
                self._layout.split_column(
                    Layout(name="header", size=3),
                    Layout(name="main"),
                    Layout(name="footer", size=3)
                )
                
                # Split main area
                self._layout["main"].split_row(
                    Layout(name="chat", ratio=3),
                    Layout(name="users", size=20)
                )
                
                # Initialize content
                self._update_layout_content()
                
                logger.debug("UI layout initialized")
            
            return self._layout
    
    def start_live_display(self) -> None:
        """Start the Rich Live display for real-time updates."""
        if self._live is None and self._layout is not None:
            self._live = Live(
                self._layout,
                console=self.console,
                refresh_per_second=self.config.target_fps,
                auto_refresh=False  # We'll control refreshes manually
            )
            self._live.start()
            logger.debug("Live display started")
    
    def stop_live_display(self) -> None:
        """Stop the Rich Live display."""
        if self._live is not None:
            self._live.stop()
            self._live = None
            logger.debug("Live display stopped")
    
    def add_chat_message(self, message: str, sender: str, timestamp: Optional[datetime] = None) -> None:
        """
        Add a chat message with optimized rendering.
        
        Args:
            message: Message content
            sender: Message sender
            timestamp: Message timestamp
        """
        formatted_message = self._format_chat_message(message, sender, timestamp)
        
        with self._lock:
            self._chat_messages.append(formatted_message)
            
            # Schedule update
            self._schedule_update(UpdateType.CHAT_MESSAGE, formatted_message, priority=2)
    
    def update_user_list(self, users: List[str]) -> None:
        """
        Update the user list with optimization.
        
        Args:
            users: List of connected users
        """
        with self._lock:
            # Check if user list actually changed
            if users != self._user_list:
                self._user_list = users.copy()
                
                # Schedule update
                self._schedule_update(UpdateType.USER_LIST, users, priority=1)
    
    def update_status(self, status: str) -> None:
        """
        Update the status bar.
        
        Args:
            status: Status message
        """
        with self._lock:
            if status != self._status_text:
                self._status_text = status
                
                # Schedule update
                self._schedule_update(UpdateType.STATUS_BAR, status, priority=3)
    
    def update_input_area(self, input_text: str) -> None:
        """
        Update the input area display.
        
        Args:
            input_text: Current input text
        """
        with self._lock:
            if input_text != self._input_text:
                self._input_text = input_text
                
                # Schedule update (low priority)
                self._schedule_update(UpdateType.INPUT_AREA, input_text, priority=0)
    
    def force_refresh(self) -> None:
        """Force a complete UI refresh."""
        with self._lock:
            self._schedule_update(UpdateType.FULL_REFRESH, None, priority=10)
    
    def get_stats(self) -> RenderStats:
        """
        Get current UI performance statistics.
        
        Returns:
            RenderStats object with current metrics
        """
        with self._lock:
            # Calculate current FPS
            current_fps = 0.0
            if self._fps_samples:
                current_fps = sum(self._fps_samples) / len(self._fps_samples)
            
            # Calculate average render time
            avg_render_time = 0.0
            if self._render_times:
                avg_render_time = sum(self._render_times) / len(self._render_times)
            
            return RenderStats(
                total_renders=self._stats.total_renders,
                total_updates=self._stats.total_updates,
                average_render_time=avg_render_time,
                current_fps=current_fps,
                peak_fps=self._stats.peak_fps,
                dropped_frames=self._stats.dropped_frames,
                cache_hits=self._stats.cache_hits,
                cache_misses=self._stats.cache_misses,
                partial_updates=self._stats.partial_updates,
                full_refreshes=self._stats.full_refreshes
            )
    
    def clear_chat_history(self) -> int:
        """
        Clear chat message history.
        
        Returns:
            Number of messages cleared
        """
        with self._lock:
            count = len(self._chat_messages)
            self._chat_messages.clear()
            
            # Force refresh to update display
            self.force_refresh()
            
            logger.info(f"Chat history cleared: {count} messages")
            return count
    
    def shutdown(self) -> None:
        """Shutdown the UI optimizer and cleanup resources."""
        logger.info("Shutting down UIOptimizer...")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Stop live display
        self.stop_live_display()
        
        # Wait for update thread
        if self._update_thread and self._update_thread.is_alive():
            self._update_thread.join(timeout=2.0)
        
        # Clear caches
        with self._lock:
            self._content_cache.clear()
            self._cache_timestamps.clear()
            self._pending_updates.clear()
        
        logger.info("UIOptimizer shutdown complete")
    
    def _schedule_update(self, update_type: UpdateType, content: Any, priority: int = 1) -> None:
        """
        Schedule a UI update with priority handling.
        
        Args:
            update_type: Type of update
            content: Update content
            priority: Update priority (higher = more important)
        """
        update = PendingUpdate(
            update_type=update_type,
            content=content,
            priority=priority
        )
        
        # Add to pending updates (will be sorted by priority)
        self._pending_updates.append(update)
        
        # Limit pending updates to prevent memory issues
        if len(self._pending_updates) > 100:
            # Remove oldest low-priority updates
            self._pending_updates = deque(
                sorted(self._pending_updates, key=lambda u: (u.priority, u.timestamp), reverse=True)[:50]
            )
    
    def _start_update_thread(self) -> None:
        """Start the UI update thread."""
        self._update_thread = threading.Thread(
            target=self._update_loop,
            name="UI-Optimizer",
            daemon=True
        )
        self._update_thread.start()
        logger.debug("UI update thread started")
    
    def _update_loop(self) -> None:
        """Main update loop for UI rendering."""
        while not self._shutdown_event.is_set():
            try:
                # Check if we have pending updates
                if not self._pending_updates:
                    time.sleep(0.01)  # Short sleep when no updates
                    continue
                
                # Check frame rate limiting
                current_time = time.time()
                time_since_last_render = current_time - self._last_render_time
                
                if self.config.enable_frame_limiting and time_since_last_render < self._frame_interval:
                    # Wait until next frame
                    sleep_time = self._frame_interval - time_since_last_render
                    time.sleep(sleep_time)
                    continue
                
                # Process pending updates
                self._process_pending_updates()
                
                # Update FPS tracking
                if time_since_last_render > 0:
                    fps = 1.0 / time_since_last_render
                    self._fps_samples.append(fps)
                    self._stats.peak_fps = max(self._stats.peak_fps, fps)
                
                self._last_render_time = current_time
                
            except Exception as e:
                logger.error(f"UI update loop error: {e}")
                time.sleep(0.1)  # Longer sleep on error
    
    def _process_pending_updates(self) -> None:
        """Process all pending UI updates."""
        with self._lock:
            if not self._pending_updates:
                return
            
            start_time = time.time()
            
            # Sort updates by priority (highest first)
            updates = sorted(self._pending_updates, key=lambda u: u.priority, reverse=True)
            self._pending_updates.clear()
            
            # Group updates by type for batching
            update_groups: Dict[UpdateType, List[PendingUpdate]] = {}
            for update in updates[:self.config.update_batch_size]:  # Limit batch size
                if update.update_type not in update_groups:
                    update_groups[update.update_type] = []
                update_groups[update.update_type].append(update)
            
            # Process each group
            needs_render = False
            for update_type, group_updates in update_groups.items():
                if self._process_update_group(update_type, group_updates):
                    needs_render = True
            
            # Render if needed
            if needs_render and self._live is not None:
                self._render_display()
            
            # Update statistics
            render_time = time.time() - start_time
            self._render_times.append(render_time)
            self._stats.total_updates += len(updates)
    
    def _process_update_group(self, update_type: UpdateType, updates: List[PendingUpdate]) -> bool:
        """
        Process a group of updates of the same type.
        
        Args:
            update_type: Type of updates
            updates: List of updates to process
            
        Returns:
            True if rendering is needed
        """
        if update_type == UpdateType.CHAT_MESSAGE:
            return self._process_chat_updates(updates)
        elif update_type == UpdateType.USER_LIST:
            return self._process_user_list_updates(updates)
        elif update_type == UpdateType.STATUS_BAR:
            return self._process_status_updates(updates)
        elif update_type == UpdateType.INPUT_AREA:
            return self._process_input_updates(updates)
        elif update_type == UpdateType.FULL_REFRESH:
            return self._process_full_refresh()
        
        return False
    
    def _process_chat_updates(self, updates: List[PendingUpdate]) -> bool:
        """Process chat message updates."""
        if not updates or self._layout is None:
            return False
        
        # Update chat panel content
        chat_content = self._create_chat_panel()
        self._layout["chat"].update(chat_content)
        
        self._stats.partial_updates += 1
        return True
    
    def _process_user_list_updates(self, updates: List[PendingUpdate]) -> bool:
        """Process user list updates."""
        if not updates or self._layout is None:
            return False
        
        # Use the most recent user list
        latest_update = max(updates, key=lambda u: u.timestamp)
        
        # Update user panel content
        user_content = self._create_user_panel(latest_update.content)
        self._layout["users"].update(user_content)
        
        self._stats.partial_updates += 1
        return True
    
    def _process_status_updates(self, updates: List[PendingUpdate]) -> bool:
        """Process status bar updates."""
        if not updates or self._layout is None:
            return False
        
        # Use the most recent status
        latest_update = max(updates, key=lambda u: u.timestamp)
        
        # Update header content
        header_content = self._create_header_panel(latest_update.content)
        self._layout["header"].update(header_content)
        
        self._stats.partial_updates += 1
        return True
    
    def _process_input_updates(self, updates: List[PendingUpdate]) -> bool:
        """Process input area updates."""
        if not updates or self._layout is None:
            return False
        
        # Use the most recent input text
        latest_update = max(updates, key=lambda u: u.timestamp)
        
        # Update footer content
        footer_content = self._create_footer_panel(latest_update.content)
        self._layout["footer"].update(footer_content)
        
        self._stats.partial_updates += 1
        return True
    
    def _process_full_refresh(self) -> bool:
        """Process full UI refresh."""
        if self._layout is None:
            return False
        
        self._update_layout_content()
        self._stats.full_refreshes += 1
        return True
    
    def _render_display(self) -> None:
        """Render the display using Rich Live."""
        try:
            if self._live is not None:
                self._live.refresh()
                self._stats.total_renders += 1
        except Exception as e:
            logger.error(f"Error rendering display: {e}")
            self._stats.dropped_frames += 1
    
    def _update_layout_content(self) -> None:
        """Update all layout content."""
        if self._layout is None:
            return
        
        # Update all panels
        self._layout["header"].update(self._create_header_panel(self._status_text))
        self._layout["chat"].update(self._create_chat_panel())
        self._layout["users"].update(self._create_user_panel(self._user_list))
        self._layout["footer"].update(self._create_footer_panel(self._input_text))
    
    def _create_header_panel(self, status: str) -> Panel:
        """Create the header panel with status information."""
        cache_key = f"header_{hash(status)}"
        
        if self.config.enable_content_caching and cache_key in self._content_cache:
            self._stats.cache_hits += 1
            return self._content_cache[cache_key]
        
        # Create header content
        header_text = Text(status or "Chat Client", style="bold blue")
        panel = Panel(header_text, title="Status", border_style="blue")
        
        # Cache the result
        if self.config.enable_content_caching:
            self._content_cache[cache_key] = panel
            self._cache_timestamps[cache_key] = datetime.now()
            self._stats.cache_misses += 1
        
        return panel
    
    def _create_chat_panel(self) -> Panel:
        """Create the chat panel with message history."""
        # Create chat content
        chat_lines = []
        for message in list(self._chat_messages)[-50:]:  # Show last 50 messages
            chat_lines.append(message)
        
        chat_text = Text("\n".join(chat_lines))
        return Panel(chat_text, title="Chat", border_style="green")
    
    def _create_user_panel(self, users: List[str]) -> Panel:
        """Create the user list panel."""
        cache_key = f"users_{hash(tuple(users))}"
        
        if self.config.enable_content_caching and cache_key in self._content_cache:
            self._stats.cache_hits += 1
            return self._content_cache[cache_key]
        
        # Create user list content
        user_text = Text("\n".join(users) if users else "No users online")
        panel = Panel(user_text, title=f"Users ({len(users)})", border_style="yellow")
        
        # Cache the result
        if self.config.enable_content_caching:
            self._content_cache[cache_key] = panel
            self._cache_timestamps[cache_key] = datetime.now()
            self._stats.cache_misses += 1
        
        return panel
    
    def _create_footer_panel(self, input_text: str) -> Panel:
        """Create the footer panel with input area."""
        footer_text = Text(f"> {input_text}", style="cyan")
        return Panel(footer_text, title="Input", border_style="cyan")
    
    def _format_chat_message(self, message: str, sender: str, timestamp: Optional[datetime] = None) -> str:
        """
        Format a chat message for display.
        
        Args:
            message: Message content
            sender: Message sender
            timestamp: Message timestamp
            
        Returns:
            Formatted message string
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        time_str = timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] {sender}: {message}"
    
    def __enter__(self) -> "UIOptimizer":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.shutdown()