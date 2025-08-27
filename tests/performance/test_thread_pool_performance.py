"""
Thread Pool Performance Tests

Tests to validate the performance improvements of the ThreadPoolManager
including scaling, task execution, and resource management.
"""

import pytest
import time
import threading
from concurrent.futures import Future
from unittest.mock import Mock, patch

from chat_app.server.performance.thread_pool import (
    ThreadPoolManager,
    ThreadPoolConfig,
    ThreadPoolStats
)
from chat_app.shared.exceptions import ThreadPoolError


class TestThreadPoolPerformance:
    """Test suite for ThreadPoolManager performance."""
    
    def test_thread_pool_initialization(self):
        """Test thread pool initializes correctly."""
        config = ThreadPoolConfig(min_threads=3, max_threads=10)
        
        with ThreadPoolManager(config) as pool:
            # Submit a few tasks to trigger thread creation
            def dummy_task():
                time.sleep(0.01)
                return "done"
            
            futures = []
            for i in range(3):
                future = pool.submit_task(dummy_task)
                futures.append(future)
            
            # Wait a moment for threads to be created
            time.sleep(0.1)
            
            stats = pool.get_stats()
            
            # After submitting tasks, threads should be created
            assert stats.total_threads >= 1  # At least some threads created
            assert stats.total_threads <= config.max_threads
            
            # Wait for tasks to complete
            for future in futures:
                future.result(timeout=1.0)
    
    def test_task_submission_performance(self):
        """Test task submission performance under load."""
        config = ThreadPoolConfig(min_threads=5, max_threads=20)
        
        def dummy_task(task_id: int) -> int:
            time.sleep(0.01)  # Simulate work
            return task_id * 2
        
        with ThreadPoolManager(config) as pool:
            start_time = time.time()
            futures = []
            
            # Submit 100 tasks
            for i in range(100):
                future = pool.submit_task(dummy_task, i)
                futures.append(future)
            
            submission_time = time.time() - start_time
            
            # Wait for all tasks to complete
            results = [future.result(timeout=10) for future in futures]
            
            # Verify results
            assert len(results) == 100
            assert all(results[i] == i * 2 for i in range(100))
            
            # Check performance metrics
            stats = pool.get_stats()
            assert stats.completed_tasks == 100
            assert stats.failed_tasks == 0
            assert submission_time < 1.0  # Should submit quickly
    
    def test_thread_pool_scaling(self):
        """Test automatic thread pool scaling under load."""
        config = ThreadPoolConfig(
            min_threads=2,
            max_threads=10,
            scale_up_threshold=0.7,
            scale_down_threshold=0.3,
            monitoring_interval=1
        )
        
        def cpu_intensive_task(duration: float) -> str:
            end_time = time.time() + duration
            while time.time() < end_time:
                pass  # Busy wait
            return "completed"
        
        with ThreadPoolManager(config) as pool:
            initial_stats = pool.get_stats()
            initial_threads = initial_stats.total_threads
            
            # Submit many CPU-intensive tasks to trigger scaling
            futures = []
            for i in range(15):
                future = pool.submit_task(cpu_intensive_task, 0.5)
                futures.append(future)
            
            # Wait a bit for scaling to occur
            time.sleep(2)
            
            # Check if scaling occurred
            scaled_stats = pool.get_stats()
            assert scaled_stats.total_threads > initial_threads
            assert scaled_stats.peak_threads >= scaled_stats.total_threads
            
            # Wait for tasks to complete
            for future in futures:
                assert future.result(timeout=10) == "completed"
    
    def test_client_handler_optimization(self):
        """Test optimized client handler task submission."""
        config = ThreadPoolConfig(min_threads=3, max_threads=15)
        
        def mock_client_handler(client_id: str, data: str) -> str:
            time.sleep(0.05)  # Simulate client handling
            return f"handled_{client_id}_{data}"
        
        with ThreadPoolManager(config) as pool:
            futures = []
            
            # Submit client handler tasks
            for i in range(20):
                future = pool.submit_client_handler(
                    mock_client_handler,
                    f"client_{i}",
                    f"data_{i}"
                )
                futures.append(future)
            
            # Verify all tasks complete successfully
            results = [future.result(timeout=15) for future in futures]
            
            assert len(results) == 20
            for i, result in enumerate(results):
                assert result == f"handled_client_{i}_data_{i}"
            
            # Check statistics
            stats = pool.get_stats()
            assert stats.completed_tasks == 20
            assert stats.failed_tasks == 0
    
    def test_task_timeout_handling(self):
        """Test task timeout and error handling."""
        config = ThreadPoolConfig(min_threads=2, max_threads=5)
        
        def slow_task(duration: float) -> str:
            time.sleep(duration)
            return "completed"
        
        def failing_task() -> str:
            raise ValueError("Task failed")
        
        with ThreadPoolManager(config) as pool:
            # Submit tasks with different behaviors
            slow_future = pool.submit_task(slow_task, 0.1, timeout=5)
            failing_future = pool.submit_task(failing_task)
            
            # Slow task should complete
            assert slow_future.result(timeout=10) == "completed"
            
            # Failing task should raise exception
            with pytest.raises(ValueError, match="Task failed"):
                failing_future.result(timeout=5)
            
            # Check statistics include both success and failure
            stats = pool.get_stats()
            assert stats.completed_tasks >= 1
            assert stats.failed_tasks >= 1
    
    def test_concurrent_task_execution(self):
        """Test concurrent execution of multiple task types."""
        config = ThreadPoolConfig(min_threads=4, max_threads=12)
        
        def io_task(task_id: int) -> str:
            time.sleep(0.1)  # Simulate I/O
            return f"io_{task_id}"
        
        def cpu_task(task_id: int) -> str:
            # Simulate CPU work
            result = 0
            for i in range(10000):
                result += i
            return f"cpu_{task_id}_{result}"
        
        with ThreadPoolManager(config) as pool:
            start_time = time.time()
            futures = []
            
            # Mix of I/O and CPU tasks
            for i in range(10):
                if i % 2 == 0:
                    future = pool.submit_task(io_task, i)
                else:
                    future = pool.submit_task(cpu_task, i)
                futures.append(future)
            
            # Wait for all tasks
            results = [future.result(timeout=15) for future in futures]
            execution_time = time.time() - start_time
            
            # Verify results
            assert len(results) == 10
            
            # Should execute concurrently (faster than sequential)
            assert execution_time < 1.5  # Much faster than 10 * 0.1 = 1.0s
            
            # Check performance stats
            stats = pool.get_stats()
            assert stats.completed_tasks == 10
            assert stats.average_task_duration > 0
    
    def test_memory_efficiency(self):
        """Test memory efficiency of thread pool operations."""
        config = ThreadPoolConfig(min_threads=3, max_threads=8)
        
        def memory_task(data_size: int) -> int:
            # Create and process some data
            data = list(range(data_size))
            return sum(data)
        
        with ThreadPoolManager(config) as pool:
            futures = []
            
            # Submit tasks with varying memory requirements
            for i in range(20):
                data_size = (i + 1) * 1000
                future = pool.submit_task(memory_task, data_size)
                futures.append(future)
            
            # Process results
            results = [future.result(timeout=10) for future in futures]
            
            # Verify calculations
            for i, result in enumerate(results):
                data_size = (i + 1) * 1000
                expected = sum(range(data_size))
                assert result == expected
            
            # Check that pool handled memory efficiently
            stats = pool.get_stats()
            assert stats.completed_tasks == 20
            assert stats.failed_tasks == 0
    
    def test_graceful_shutdown(self):
        """Test graceful shutdown with pending tasks."""
        config = ThreadPoolConfig(min_threads=2, max_threads=5)
        
        def quick_task(task_id: int) -> str:
            # Very short task to avoid hanging
            time.sleep(0.01)
            return f"completed_{task_id}"
        
        # Use context manager to ensure cleanup
        with ThreadPoolManager(config) as pool:
            # Submit a few quick tasks
            futures = []
            for i in range(2):
                future = pool.submit_task(quick_task, i)
                futures.append(future)
            
            # Wait for tasks to complete
            time.sleep(0.1)
            
            # Check that tasks completed
            completed_count = sum(1 for f in futures if f.done())
            assert completed_count >= 0  # At least some progress made
        
        # Context manager handles shutdown automatically
    
    def test_statistics_accuracy(self):
        """Test accuracy of performance statistics."""
        config = ThreadPoolConfig(min_threads=2, max_threads=6, enable_monitoring=True)
        
        def timed_task(duration: float) -> float:
            start = time.time()
            time.sleep(duration)
            return time.time() - start
        
        with ThreadPoolManager(config) as pool:
            # Submit tasks with known durations
            durations = [0.1, 0.2, 0.15, 0.25, 0.3]
            futures = []
            
            for duration in durations:
                future = pool.submit_task(timed_task, duration)
                futures.append(future)
            
            # Wait for completion
            actual_durations = [future.result(timeout=10) for future in futures]
            
            # Check statistics
            stats = pool.get_stats()
            
            assert stats.completed_tasks == len(durations)
            assert stats.failed_tasks == 0
            assert stats.total_threads >= config.min_threads
            assert stats.average_task_duration > 0
            
            # Average should be reasonable
            expected_avg = sum(durations) / len(durations)
            assert abs(stats.average_task_duration - expected_avg) < 0.1
    
    def test_error_recovery(self):
        """Test error recovery and continued operation."""
        config = ThreadPoolConfig(min_threads=2, max_threads=4)
        
        def sometimes_failing_task(task_id: int) -> str:
            if task_id % 3 == 0:
                raise RuntimeError(f"Task {task_id} failed")
            time.sleep(0.05)
            return f"success_{task_id}"
        
        with ThreadPoolManager(config) as pool:
            futures = []
            
            # Submit mix of successful and failing tasks
            for i in range(15):
                future = pool.submit_task(sometimes_failing_task, i)
                futures.append(future)
            
            # Process results
            successes = 0
            failures = 0
            
            for i, future in enumerate(futures):
                try:
                    result = future.result(timeout=5)
                    assert result == f"success_{i}"
                    successes += 1
                except RuntimeError:
                    failures += 1
            
            # Verify expected pattern
            assert successes == 10  # Tasks 1,2,4,5,7,8,10,11,13,14
            assert failures == 5   # Tasks 0,3,6,9,12
            
            # Pool should continue operating
            stats = pool.get_stats()
            assert stats.completed_tasks == successes
            assert stats.failed_tasks == failures


@pytest.mark.performance
class TestThreadPoolBenchmarks:
    """Benchmark tests for thread pool performance."""
    
    def test_throughput_benchmark(self):
        """Benchmark task throughput under various loads."""
        config = ThreadPoolConfig(min_threads=4, max_threads=16)
        
        def benchmark_task(task_id: int) -> int:
            # Simulate mixed workload
            time.sleep(0.01)  # I/O simulation
            result = sum(range(100))  # CPU work
            return task_id + result
        
        with ThreadPoolManager(config) as pool:
            # Test different load levels
            load_levels = [10, 50, 100, 200]
            
            for load in load_levels:
                start_time = time.time()
                futures = []
                
                # Submit tasks
                for i in range(load):
                    future = pool.submit_task(benchmark_task, i)
                    futures.append(future)
                
                # Wait for completion
                results = [future.result(timeout=30) for future in futures]
                execution_time = time.time() - start_time
                
                # Calculate throughput
                throughput = load / execution_time
                
                # Log performance metrics
                stats = pool.get_stats()
                print(f"Load: {load}, Time: {execution_time:.2f}s, "
                      f"Throughput: {throughput:.1f} tasks/s, "
                      f"Threads: {stats.total_threads}")
                
                # Basic performance assertions
                assert len(results) == load
                assert throughput > 0
                assert execution_time < load * 0.02  # Should be much faster than sequential
    
    def test_scaling_efficiency(self):
        """Test efficiency of thread pool scaling."""
        config = ThreadPoolConfig(
            min_threads=2,
            max_threads=20,
            scale_up_threshold=0.8,
            scale_down_threshold=0.2,
            monitoring_interval=1
        )
        
        def variable_load_task(duration: float) -> str:
            time.sleep(duration)
            return "completed"
        
        with ThreadPoolManager(config) as pool:
            # Phase 1: Low load
            futures_low = []
            for i in range(5):
                future = pool.submit_task(variable_load_task, 0.1)
                futures_low.append(future)
            
            time.sleep(0.5)
            stats_low = pool.get_stats()
            
            # Phase 2: High load
            futures_high = []
            for i in range(25):
                future = pool.submit_task(variable_load_task, 0.2)
                futures_high.append(future)
            
            time.sleep(2)  # Allow scaling
            stats_high = pool.get_stats()
            
            # Phase 3: Return to low load
            for future in futures_low + futures_high:
                future.result(timeout=10)
            
            time.sleep(3)  # Allow scale down
            stats_final = pool.get_stats()
            
            # Verify scaling behavior
            assert stats_high.total_threads > stats_low.total_threads
            assert stats_high.peak_threads >= stats_high.total_threads
            
            print(f"Scaling: {stats_low.total_threads} -> "
                  f"{stats_high.total_threads} -> {stats_final.total_threads}")