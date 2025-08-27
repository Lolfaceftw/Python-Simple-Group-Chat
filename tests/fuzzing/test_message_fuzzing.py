"""
Fuzzing tests for message content using hypothesis library.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant
import string

from chat_app.shared.utils import validate_message, validate_username, sanitize_input
from chat_app.shared.models import Message, MessageType
from chat_app.server.security.validator import InputValidator


class TestMessageContentFuzzing:
    """Fuzzing tests for message content validation and processing."""
    
    @given(st.text())
    @settings(max_examples=200)
    def test_validate_message_never_crashes(self, message_content):
        """Test that message validation never crashes regardless of input."""
        try:
            is_valid, error_msg = validate_message(message_content)
            
            # Validation should always return a boolean and optional string
            assert isinstance(is_valid, bool)
            assert error_msg is None or isinstance(error_msg, str)
            
            # If invalid, should have an error message
            if not is_valid:
                assert error_msg is not None
                assert len(error_msg) > 0
                
        except Exception as e:
            pytest.fail(f"validate_message crashed with input '{repr(message_content)}': {e}")
    
    @given(st.text(min_size=1, max_size=1000))
    @settings(max_examples=100)
    def test_valid_messages_properties(self, message_content):
        """Test properties that should hold for valid messages."""
        assume(len(message_content) <= 1000)  # Within length limit
        assume('\x00' not in message_content)  # No null bytes
        assume(not any(ord(c) < 32 and c not in '\t\n\r' for c in message_content))  # No control chars
        
        is_valid, error_msg = validate_message(message_content)
        
        if is_valid:
            # Valid messages should have no error message
            assert error_msg is None
            
            # Should be able to create Message object
            message = Message(
                content=message_content,
                sender="testuser",
                message_type=MessageType.CHAT
            )
            assert message.content == message_content
    
    @given(st.text())
    @settings(max_examples=200)
    def test_sanitize_input_never_crashes(self, input_text):
        """Test that input sanitization never crashes."""
        try:
            sanitized = sanitize_input(input_text)
            
            # Should always return a string
            assert isinstance(sanitized, str)
            
            # Sanitized input should not contain control characters (except allowed ones)
            for char in sanitized:
                if ord(char) < 32:
                    assert char in '\t\n\r', f"Unexpected control character: {repr(char)}"
                    
        except Exception as e:
            pytest.fail(f"sanitize_input crashed with input '{repr(input_text)}': {e}")
    
    @given(st.text(alphabet=string.printable))
    @settings(max_examples=100)
    def test_sanitize_preserves_printable_characters(self, input_text):
        """Test that sanitization preserves printable characters."""
        sanitized = sanitize_input(input_text)
        
        # All characters in sanitized output should be printable or allowed whitespace
        for char in sanitized:
            assert char.isprintable() or char in '\t\n\r'
    
    @given(st.text(min_size=0, max_size=2000))
    @settings(max_examples=100)
    def test_message_length_validation_consistency(self, message_content):
        """Test that message length validation is consistent."""
        is_valid, error_msg = validate_message(message_content)
        
        if len(message_content) == 0:
            # Empty messages should be invalid
            assert not is_valid
            assert "empty" in error_msg.lower()
        elif len(message_content) > 1000:
            # Too long messages should be invalid
            assert not is_valid
            assert "exceed" in error_msg.lower() or "long" in error_msg.lower()
    
    @given(st.binary())
    @settings(max_examples=100)
    def test_binary_data_handling(self, binary_data):
        """Test handling of binary data that might be decoded as text."""
        try:
            # Try to decode binary data as UTF-8
            try:
                text_data = binary_data.decode('utf-8', errors='ignore')
            except UnicodeDecodeError:
                text_data = ""
            
            # Validation should handle the decoded text gracefully
            is_valid, error_msg = validate_message(text_data)
            assert isinstance(is_valid, bool)
            
            # Sanitization should handle it gracefully
            sanitized = sanitize_input(text_data)
            assert isinstance(sanitized, str)
            
        except Exception as e:
            pytest.fail(f"Binary data handling failed with {repr(binary_data)}: {e}")


class TestUsernameFuzzing:
    """Fuzzing tests for username validation."""
    
    @given(st.text())
    @settings(max_examples=200)
    def test_validate_username_never_crashes(self, username):
        """Test that username validation never crashes."""
        try:
            is_valid, error_msg = validate_username(username)
            
            assert isinstance(is_valid, bool)
            assert error_msg is None or isinstance(error_msg, str)
            
            if not is_valid:
                assert error_msg is not None
                assert len(error_msg) > 0
                
        except Exception as e:
            pytest.fail(f"validate_username crashed with input '{repr(username)}': {e}")
    
    @given(st.text(alphabet=string.ascii_letters + string.digits + '_- ', min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_valid_username_properties(self, username):
        """Test properties of valid usernames."""
        # Skip usernames with leading/trailing whitespace
        assume(username.strip() == username)
        assume(len(username) > 0)
        
        is_valid, error_msg = validate_username(username)
        
        # Should be valid if it meets all criteria
        if is_valid:
            assert error_msg is None
            assert 1 <= len(username) <= 50
            assert username.strip() == username
    
    @given(st.text(min_size=51, max_size=100))
    @settings(max_examples=50)
    def test_long_username_rejection(self, long_username):
        """Test that overly long usernames are rejected."""
        is_valid, error_msg = validate_username(long_username)
        
        assert not is_valid
        assert "exceed" in error_msg.lower() or "long" in error_msg.lower()
    
    @given(st.text(alphabet=string.punctuation.replace('_', '').replace('-', ''), min_size=1, max_size=20))
    @settings(max_examples=50)
    def test_invalid_character_rejection(self, username_with_special_chars):
        """Test that usernames with invalid characters are rejected."""
        # Skip if it only contains allowed special characters
        assume(any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- ' 
                  for c in username_with_special_chars))
        
        is_valid, error_msg = validate_username(username_with_special_chars)
        
        assert not is_valid
        assert "contain" in error_msg.lower() or "character" in error_msg.lower()


class TestInputValidatorFuzzing:
    """Fuzzing tests for the InputValidator class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)  # Use non-strict mode for fuzzing
    
    @given(st.text(), st.sampled_from(['username', 'message', 'command']))
    @settings(max_examples=200)
    def test_validator_never_crashes(self, input_data, input_type):
        """Test that InputValidator never crashes."""
        try:
            if input_type == 'username':
                result = self.validator.validate_username(input_data)
            elif input_type == 'message':
                result = self.validator.validate_message(input_data)
            elif input_type == 'command':
                result = self.validator.validate_command(input_data)
            
            assert isinstance(result.is_valid, bool)
            assert isinstance(result.errors, list)
            
        except Exception as e:
            pytest.fail(f"InputValidator crashed with '{repr(input_data)}' of type '{input_type}': {e}")
    
    @given(st.text())
    @settings(max_examples=100)
    def test_sanitize_never_crashes(self, input_data):
        """Test that sanitization never crashes."""
        try:
            # The InputValidator doesn't have a public sanitize method, 
            # so we'll test through validation which includes sanitization
            result = self.validator.validate_message(input_data)
            assert isinstance(result.is_valid, bool)
            if result.sanitized_value is not None:
                assert isinstance(result.sanitized_value, str)
            
        except Exception as e:
            pytest.fail(f"Sanitization crashed with '{repr(input_data)}': {e}")


class MessageProcessingStateMachine(RuleBasedStateMachine):
    """Stateful fuzzing for message processing workflows."""
    
    def __init__(self):
        super().__init__()
        self.messages = []
        self.validator = InputValidator()
        self.total_processed = 0
        self.total_rejected = 0
    
    @rule(content=st.text(min_size=1, max_size=1000), 
          sender=st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20))
    def add_message(self, content, sender):
        """Add a message to the processing queue."""
        try:
            # Validate the message - handle validation exceptions
            try:
                content_result = self.validator.validate_message(content)
                is_valid_content = content_result.is_valid
            except Exception:
                is_valid_content = False
            
            try:
                sender_result = self.validator.validate_username(sender)
                is_valid_sender = sender_result.is_valid
            except Exception:
                is_valid_sender = False
            
            if is_valid_content and is_valid_sender:
                message = Message(
                    content=content,
                    sender=sender,
                    message_type=MessageType.CHAT
                )
                self.messages.append(message)
                self.total_processed += 1
            else:
                self.total_rejected += 1
                
        except Exception as e:
            # Should not crash during message processing
            pytest.fail(f"Message processing crashed: {e}")
    
    @rule()
    def clear_messages(self):
        """Clear all messages."""
        self.messages.clear()
    
    @rule(count=st.integers(min_value=0, max_value=10))
    def get_recent_messages(self, count):
        """Get recent messages."""
        try:
            recent = self.messages[-count:] if count > 0 else []
            assert len(recent) <= len(self.messages)
            assert len(recent) <= count
        except Exception as e:
            pytest.fail(f"Getting recent messages failed: {e}")
    
    @invariant()
    def messages_are_valid(self):
        """Invariant: all stored messages should be valid."""
        for message in self.messages:
            assert isinstance(message, Message)
            assert isinstance(message.content, str)
            assert isinstance(message.sender, str)
            assert len(message.content) > 0
            assert len(message.sender) > 0
    
    @invariant()
    def counters_are_consistent(self):
        """Invariant: counters should be consistent."""
        assert self.total_processed >= 0
        assert self.total_rejected >= 0
        assert len(self.messages) <= self.total_processed


# Create the test class for the state machine
TestMessageProcessingStateMachine = MessageProcessingStateMachine.TestCase


class TestProtocolFuzzing:
    """Fuzzing tests for protocol message parsing."""
    
    @given(st.text(), st.text())
    @settings(max_examples=100)
    def test_message_protocol_parsing(self, msg_type, payload):
        """Test protocol message parsing with arbitrary inputs."""
        try:
            # Create protocol string
            protocol_str = f"{msg_type}|{payload}"
            
            # Try to parse it
            message = Message.from_protocol_string(protocol_str, sender="fuzzer")
            
            # Should always create a valid Message object
            assert isinstance(message, Message)
            assert isinstance(message.content, str)
            assert isinstance(message.sender, str)
            assert isinstance(message.message_type, MessageType)
            
        except Exception as e:
            pytest.fail(f"Protocol parsing crashed with '{repr(protocol_str)}': {e}")
    
    @given(st.text(alphabet=string.printable, min_size=0, max_size=100))
    @settings(max_examples=100)
    def test_protocol_string_generation(self, content):
        """Test protocol string generation with various content."""
        try:
            message = Message(
                content=content,
                sender="fuzzer",
                message_type=MessageType.CHAT
            )
            
            protocol_str = message.to_protocol_string()
            
            # Should always generate a valid protocol string
            assert isinstance(protocol_str, str)
            assert "|" in protocol_str
            assert protocol_str.startswith("MSG|")
            
        except Exception as e:
            pytest.fail(f"Protocol generation crashed with content '{repr(content)}': {e}")


if __name__ == "__main__":
    # Run some basic fuzzing tests if executed directly
    import sys
    sys.path.insert(0, '.')
    
    test = TestMessageContentFuzzing()
    
    # Run a few examples manually
    test.test_validate_message_never_crashes("Hello, world!")
    test.test_validate_message_never_crashes("")
    test.test_validate_message_never_crashes("x" * 2000)
    test.test_sanitize_input_never_crashes("Test\x00\x01message")
    
    print("Basic fuzzing tests passed!")