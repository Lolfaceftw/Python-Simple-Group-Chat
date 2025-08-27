"""
Fuzzing tests for network protocols and packet handling.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant
import string
import socket
from unittest.mock import Mock, patch

from chat_app.shared.utils import parse_message_protocol, format_message_protocol
from chat_app.shared.models import Message, MessageType, NetworkMessage
from chat_app.server.security.connection_limiter import ConnectionLimiter


class TestProtocolFuzzing:
    """Fuzzing tests for network protocol parsing and generation."""
    
    @given(st.text(), st.text())
    @settings(max_examples=200)
    def test_protocol_parsing_robustness(self, msg_type, payload):
        """Test protocol message parsing with arbitrary inputs."""
        try:
            msg_type_part, payload_part = parse_message_protocol(f"{msg_type}|{payload}")
            
            # Should always return two strings
            assert isinstance(msg_type_part, str)
            assert isinstance(payload_part, str)
            
            # For edge cases where msg_type contains '|', the parsing behavior is defined
            # by the implementation - we just verify it doesn't crash and returns strings
            
        except Exception as e:
            pytest.fail(f"Protocol parsing crashed with type='{repr(msg_type)}', payload='{repr(payload)}': {e}")
    
    @given(st.text(), st.text())
    @settings(max_examples=100)
    def test_protocol_generation_robustness(self, msg_type, payload):
        """Test protocol message generation with arbitrary inputs."""
        try:
            protocol_str = format_message_protocol(msg_type, payload)
            
            # Should always return a string
            assert isinstance(protocol_str, str)
            
            # Should contain the separator
            assert '|' in protocol_str
            
            # Should be parseable back - but for edge cases where msg_type contains '|',
            # the round-trip may not be exact due to parsing ambiguity
            parsed_type, parsed_payload = parse_message_protocol(protocol_str)
            assert isinstance(parsed_type, str)
            assert isinstance(parsed_payload, str)
            
        except Exception as e:
            pytest.fail(f"Protocol generation crashed with type='{repr(msg_type)}', payload='{repr(payload)}': {e}")
    
    @given(st.text(alphabet='|', min_size=0, max_size=10), st.text(), st.text())
    @settings(max_examples=50)
    def test_multiple_separators_handling(self, separators, msg_type, payload):
        """Test handling of multiple separator characters."""
        try:
            # Create message with multiple separators
            malformed_message = f"{msg_type}{separators}{payload}"
            
            parsed_type, parsed_payload = parse_message_protocol(malformed_message)
            
            # Should handle gracefully
            assert isinstance(parsed_type, str)
            assert isinstance(parsed_payload, str)
            
        except Exception as e:
            pytest.fail(f"Multiple separator handling crashed with '{repr(malformed_message)}': {e}")
    
    @given(st.binary(min_size=1, max_size=1000))
    @settings(max_examples=100)
    def test_binary_protocol_data(self, binary_data):
        """Test protocol handling with binary data."""
        try:
            # Try to decode binary data as text
            try:
                text_data = binary_data.decode('utf-8', errors='ignore')
            except UnicodeDecodeError:
                text_data = binary_data.decode('latin1', errors='ignore')
            
            if text_data:  # Only test non-empty decoded strings
                # Try to parse as protocol message
                if '|' in text_data:
                    parsed_type, parsed_payload = parse_message_protocol(text_data)
                    assert isinstance(parsed_type, str)
                    assert isinstance(parsed_payload, str)
                
        except Exception as e:
            pytest.fail(f"Binary protocol handling crashed with {repr(binary_data)}: {e}")


class TestNetworkMessageFuzzing:
    """Fuzzing tests for NetworkMessage handling."""
    
    @given(st.binary())
    @settings(max_examples=100)
    def test_network_message_creation(self, binary_data):
        """Test NetworkMessage creation with arbitrary binary data."""
        try:
            message = NetworkMessage(data=binary_data)
            
            # Should always create a valid object
            assert isinstance(message, NetworkMessage)
            assert message.data == binary_data
            assert message.source_address is None
            
        except Exception as e:
            pytest.fail(f"NetworkMessage creation crashed with {repr(binary_data)}: {e}")
    
    @given(st.binary())
    @settings(max_examples=100)
    def test_network_message_decoding(self, binary_data):
        """Test NetworkMessage decoding with arbitrary binary data."""
        try:
            message = NetworkMessage(data=binary_data)
            
            # Try to decode - should handle errors gracefully
            try:
                decoded = message.decode()
                assert isinstance(decoded, str)
            except UnicodeDecodeError:
                # Expected for some binary data
                pass
                
        except Exception as e:
            pytest.fail(f"NetworkMessage decoding crashed with {repr(binary_data)}: {e}")
    
    @given(st.text())
    @settings(max_examples=100)
    def test_network_message_from_string(self, text_data):
        """Test NetworkMessage creation from string data."""
        try:
            message = NetworkMessage.from_string(text_data)
            
            # Should create valid message
            assert isinstance(message, NetworkMessage)
            assert isinstance(message.data, bytes)
            
            # Should be decodable back to original string
            decoded = message.decode()
            assert decoded == text_data
            
        except Exception as e:
            pytest.fail(f"NetworkMessage from_string crashed with '{repr(text_data)}': {e}")


class TestConnectionLimiterFuzzing:
    """Fuzzing tests for connection limiting and security."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = ConnectionLimiter(
            max_connections_per_ip=10,
            max_total_connections=100
        )
    
    def teardown_method(self):
        """Clean up test fixtures."""
        if hasattr(self, 'limiter'):
            self.limiter.shutdown()
    
    @given(st.text(alphabet=string.ascii_letters + string.digits + '.-', min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_connection_id_fuzzing(self, connection_id):
        """Test connection registration with arbitrary connection IDs."""
        try:
            # Generate a valid IP for testing
            ip_address = "192.168.1.100"
            
            # Try to register connection
            can_accept, reason = self.limiter.can_accept_connection(ip_address)
            
            if can_accept:
                conn_info = self.limiter.register_connection(connection_id, ip_address)
                assert conn_info is not None
                assert conn_info.connection_id == connection_id
                
                # Clean up
                self.limiter.unregister_connection(connection_id)
            
        except Exception as e:
            pytest.fail(f"Connection ID fuzzing crashed with '{repr(connection_id)}': {e}")
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_ip_address_fuzzing(self, ip_like_string):
        """Test connection limiting with IP-like strings."""
        try:
            connection_id = "test_conn"
            
            # Try to check if connection can be accepted
            can_accept, reason = self.limiter.can_accept_connection(ip_like_string)
            
            # Should always return a boolean and optional string
            assert isinstance(can_accept, bool)
            assert reason is None or isinstance(reason, str)
            
            if can_accept:
                try:
                    conn_info = self.limiter.register_connection(connection_id, ip_like_string)
                    if conn_info:
                        self.limiter.unregister_connection(connection_id)
                except Exception:
                    # Some IP-like strings might cause registration to fail, which is fine
                    pass
            
        except Exception as e:
            pytest.fail(f"IP address fuzzing crashed with '{repr(ip_like_string)}': {e}")
    
    @given(st.lists(st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20), 
                    min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_bulk_connection_fuzzing(self, connection_ids):
        """Test bulk connection registration and cleanup."""
        try:
            ip_address = "192.168.1.200"
            registered_connections = []
            
            # Try to register all connections
            for conn_id in connection_ids:
                try:
                    can_accept, _ = self.limiter.can_accept_connection(ip_address)
                    if can_accept:
                        conn_info = self.limiter.register_connection(conn_id, ip_address)
                        if conn_info:
                            registered_connections.append(conn_id)
                except Exception:
                    # Some connections might fail due to limits, which is expected
                    pass
            
            # Clean up all registered connections
            for conn_id in registered_connections:
                try:
                    self.limiter.unregister_connection(conn_id)
                except Exception:
                    # Cleanup might fail for some connections, which is acceptable
                    pass
            
        except Exception as e:
            pytest.fail(f"Bulk connection fuzzing crashed with {len(connection_ids)} connections: {e}")


class NetworkProtocolStateMachine(RuleBasedStateMachine):
    """Stateful fuzzing for network protocol handling."""
    
    def __init__(self):
        super().__init__()
        self.messages = []
        self.parsed_messages = []
        self.protocol_strings = []
    
    @rule(content=st.text(min_size=1, max_size=200), 
          sender=st.text(alphabet=string.ascii_letters, min_size=1, max_size=20))
    def create_message(self, content, sender):
        """Create a new message."""
        try:
            message = Message(
                content=content,
                sender=sender,
                message_type=MessageType.CHAT
            )
            self.messages.append(message)
            
        except Exception as e:
            pytest.fail(f"Message creation failed: {e}")
    
    @rule()
    def convert_to_protocol(self):
        """Convert messages to protocol strings."""
        try:
            for message in self.messages[-5:]:  # Convert last 5 messages
                protocol_str = message.to_protocol_string()
                self.protocol_strings.append(protocol_str)
            
        except Exception as e:
            pytest.fail(f"Protocol conversion failed: {e}")
    
    @rule()
    def parse_protocol_strings(self):
        """Parse protocol strings back to messages."""
        try:
            for protocol_str in self.protocol_strings[-5:]:  # Parse last 5 protocol strings
                parsed_type, parsed_payload = parse_message_protocol(protocol_str)
                
                # Create message from parsed data
                message = Message.from_protocol_string(protocol_str, sender="parser")
                self.parsed_messages.append(message)
                
        except Exception as e:
            pytest.fail(f"Protocol parsing failed: {e}")
    
    @rule()
    def clear_old_data(self):
        """Clear old data to prevent memory issues."""
        # Keep only recent data
        self.messages = self.messages[-20:]
        self.parsed_messages = self.parsed_messages[-20:]
        self.protocol_strings = self.protocol_strings[-20:]
    
    @invariant()
    def messages_are_valid(self):
        """Invariant: all messages should be valid."""
        for message in self.messages:
            assert isinstance(message, Message)
            assert isinstance(message.content, str)
            assert isinstance(message.sender, str)
            assert len(message.content) > 0
            assert len(message.sender) > 0
    
    @invariant()
    def protocol_strings_are_valid(self):
        """Invariant: all protocol strings should be valid."""
        for protocol_str in self.protocol_strings:
            assert isinstance(protocol_str, str)
            assert '|' in protocol_str
            assert len(protocol_str) > 0
    
    @invariant()
    def parsed_messages_are_valid(self):
        """Invariant: all parsed messages should be valid."""
        for message in self.parsed_messages:
            assert isinstance(message, Message)
            assert isinstance(message.content, str)
            assert isinstance(message.sender, str)


# Create the test class for the state machine
TestNetworkProtocolStateMachine = NetworkProtocolStateMachine.TestCase


class TestMalformedPacketFuzzing:
    """Fuzzing tests for malformed network packets."""
    
    @given(st.binary(min_size=1, max_size=4096))
    @settings(max_examples=100)
    def test_malformed_packet_handling(self, packet_data):
        """Test handling of malformed network packets."""
        try:
            # Simulate receiving a malformed packet
            network_message = NetworkMessage(data=packet_data)
            
            # Try to decode and process
            try:
                decoded = network_message.decode()
                
                # If decodable, try to parse as protocol message
                if '|' in decoded:
                    msg_type, payload = parse_message_protocol(decoded)
                    assert isinstance(msg_type, str)
                    assert isinstance(payload, str)
                    
            except UnicodeDecodeError:
                # Expected for binary data that's not valid UTF-8
                pass
                
        except Exception as e:
            pytest.fail(f"Malformed packet handling crashed with {repr(packet_data)}: {e}")
    
    @given(st.text(alphabet=string.printable + '\x00\x01\x02\x03', min_size=1, max_size=1000))
    @settings(max_examples=100)
    def test_mixed_content_packets(self, mixed_content):
        """Test packets with mixed printable and control characters."""
        try:
            # Create network message with mixed content
            packet_data = mixed_content.encode('utf-8', errors='ignore')
            network_message = NetworkMessage(data=packet_data)
            
            # Should handle gracefully
            assert isinstance(network_message, NetworkMessage)
            
            # Try to decode
            try:
                decoded = network_message.decode()
                assert isinstance(decoded, str)
            except UnicodeDecodeError:
                # Some mixed content might not be decodable
                pass
                
        except Exception as e:
            pytest.fail(f"Mixed content packet handling crashed with '{repr(mixed_content)}': {e}")
    
    @given(st.integers(min_value=0, max_value=10000))
    @settings(max_examples=50)
    def test_packet_size_boundaries(self, packet_size):
        """Test handling of various packet sizes."""
        try:
            # Create packet of specific size
            packet_data = b'A' * packet_size
            
            # Should handle any size gracefully
            network_message = NetworkMessage(data=packet_data)
            assert isinstance(network_message, NetworkMessage)
            assert len(network_message.data) == packet_size
            
            # Decoding should work for ASCII data
            if packet_size > 0:
                decoded = network_message.decode()
                assert len(decoded) == packet_size
                assert decoded == 'A' * packet_size
            
        except Exception as e:
            pytest.fail(f"Packet size boundary test crashed with size {packet_size}: {e}")


if __name__ == "__main__":
    # Run some basic fuzzing tests if executed directly
    import sys
    sys.path.insert(0, '.')
    
    test = TestProtocolFuzzing()
    
    # Run a few examples manually
    test.test_protocol_parsing_robustness("MSG", "Hello World")
    test.test_protocol_generation_robustness("SRV", "Server message")
    test.test_multiple_separators_handling("|||", "MSG", "payload")
    
    print("Network fuzzing tests passed!")