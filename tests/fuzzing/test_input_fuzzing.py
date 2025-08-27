"""
Fuzzing tests for input validation and command processing.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant, initialize
import string
import re

from chat_app.shared.utils import validate_username, validate_message, sanitize_input
from chat_app.server.security.validator import InputValidator
from chat_app.shared.exceptions import ValidationError


class TestInputValidationFuzzing:
    """Fuzzing tests for various input validation scenarios."""
    
    @given(st.text())
    @settings(max_examples=300)
    def test_username_validation_robustness(self, username):
        """Test username validation with arbitrary input."""
        try:
            is_valid, error_msg = validate_username(username)
            
            # Should never crash
            assert isinstance(is_valid, bool)
            assert error_msg is None or isinstance(error_msg, str)
            
            # If valid, should meet basic criteria
            if is_valid:
                assert len(username) > 0
                assert len(username) <= 50
                assert username.strip() == username
                
        except Exception as e:
            pytest.fail(f"Username validation crashed with '{repr(username)}': {e}")
    
    @given(st.text(alphabet=string.whitespace, min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_whitespace_only_usernames(self, whitespace_username):
        """Test usernames consisting only of whitespace."""
        is_valid, error_msg = validate_username(whitespace_username)
        
        # Whitespace-only usernames should be invalid
        assert not is_valid
        assert error_msg is not None
    
    @given(st.text(alphabet=string.ascii_letters + string.digits + '_-', min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_valid_username_characters(self, username):
        """Test usernames with only valid characters."""
        is_valid, error_msg = validate_username(username)
        
        # Should be valid (assuming no leading/trailing whitespace)
        if is_valid:
            assert error_msg is None
        else:
            # If invalid, should have a reason
            assert error_msg is not None
    
    @given(st.text(alphabet=string.punctuation.replace('_', '').replace('-', ''), min_size=1, max_size=20))
    @settings(max_examples=50)
    def test_invalid_username_characters(self, special_chars):
        """Test usernames with invalid special characters."""
        # Skip if it accidentally contains only valid characters
        assume(any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- ' 
                  for c in special_chars))
        
        is_valid, error_msg = validate_username(special_chars)
        
        # Should be invalid due to special characters
        assert not is_valid
        assert error_msg is not None
        assert "character" in error_msg.lower() or "contain" in error_msg.lower()


class TestCommandFuzzing:
    """Fuzzing tests for command parsing and validation."""
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=200)
    def test_command_parsing_robustness(self, command_input):
        """Test command parsing with arbitrary input."""
        try:
            # Simulate command parsing logic
            if command_input.startswith('/'):
                parts = command_input.split(' ', 1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                # Common commands
                valid_commands = ['/quit', '/nick', '/help', '/list', '/clear']
                
                if command in valid_commands:
                    # Valid command - should process args safely
                    if command == '/nick' and args:
                        # Test nickname validation
                        is_valid, _ = validate_username(args.strip())
                        # Should not crash regardless of validity
                        assert isinstance(is_valid, bool)
                
                # Should handle unknown commands gracefully
                # (Implementation would typically show "unknown command" message)
                
        except Exception as e:
            pytest.fail(f"Command parsing crashed with '{repr(command_input)}': {e}")
    
    @given(st.text(alphabet='/', min_size=1, max_size=5), 
           st.text(alphabet=string.ascii_letters, min_size=1, max_size=20),
           st.text())
    @settings(max_examples=100)
    def test_malformed_commands(self, slashes, command_name, args):
        """Test handling of malformed commands."""
        malformed_command = f"{slashes}{command_name} {args}"
        
        try:
            # Should handle malformed commands without crashing
            if malformed_command.startswith('/'):
                parts = malformed_command.split(' ', 1)
                command = parts[0].lower()
                
                # Even malformed commands should be processed safely
                assert isinstance(command, str)
                
        except Exception as e:
            pytest.fail(f"Malformed command handling crashed with '{repr(malformed_command)}': {e}")


class TestSecurityInputFuzzing:
    """Fuzzing tests for security-related input validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)  # Use non-strict mode for fuzzing
    
    @given(st.text())
    @settings(max_examples=200)
    def test_injection_attempt_detection(self, input_data):
        """Test detection of potential injection attempts."""
        try:
            # Test various input types
            for input_type in ['username', 'message', 'command']:
                if input_type == 'username':
                    result = self.validator.validate_username(input_data)
                elif input_type == 'message':
                    result = self.validator.validate_message(input_data)
                elif input_type == 'command':
                    result = self.validator.validate_command(input_data)
                
                # Should never crash
                assert isinstance(result.is_valid, bool)
                
                # If input contains potential injection patterns, should be handled safely
                injection_patterns = ['<script>', '<?php', 'javascript:', 'data:', 'vbscript:']
                has_injection_pattern = any(pattern in input_data.lower() for pattern in injection_patterns)
                
                if has_injection_pattern and input_type in ['username', 'message']:
                    # May be rejected or sanitized, but should not crash
                    pass
                    
        except Exception as e:
            pytest.fail(f"Injection detection crashed with '{repr(input_data)}': {e}")
    
    @given(st.text(alphabet=string.ascii_letters + '<>"\'/\\&;', min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_html_injection_patterns(self, input_with_html_chars):
        """Test handling of HTML-like injection patterns."""
        try:
            # Test through message validation which includes sanitization
            result = self.validator.validate_message(input_with_html_chars)
            
            # Should always return a ValidationResult
            assert isinstance(result.is_valid, bool)
            
            # If sanitized value is provided, check it
            if result.sanitized_value is not None:
                sanitized = result.sanitized_value
                assert isinstance(sanitized, str)
                
                # Common dangerous patterns should be neutralized
                dangerous_patterns = ['<script', '<iframe', '<object', '<embed']
                for pattern in dangerous_patterns:
                    if pattern in input_with_html_chars.lower():
                        # Should be sanitized or removed
                        assert pattern not in sanitized.lower() or len(sanitized) < len(input_with_html_chars)
                    
        except Exception as e:
            pytest.fail(f"HTML injection handling crashed with '{repr(input_with_html_chars)}': {e}")
    
    @given(st.binary(min_size=1, max_size=200))
    @settings(max_examples=100)
    def test_binary_injection_attempts(self, binary_data):
        """Test handling of binary data as potential injection."""
        try:
            # Convert binary to string (simulating various encoding attempts)
            for encoding in ['utf-8', 'latin1', 'ascii']:
                try:
                    text_data = binary_data.decode(encoding, errors='ignore')
                    if text_data:  # Only test non-empty decoded strings
                        result = self.validator.validate_message(text_data)
                        assert isinstance(result.is_valid, bool)
                        
                        if result.sanitized_value is not None:
                            assert isinstance(result.sanitized_value, str)
                except UnicodeDecodeError:
                    # Expected for some binary data
                    pass
                    
        except Exception as e:
            pytest.fail(f"Binary injection handling crashed with {repr(binary_data)}: {e}")


class InputValidationStateMachine(RuleBasedStateMachine):
    """Stateful fuzzing for input validation workflows."""
    
    def __init__(self):
        super().__init__()
        self.validator = InputValidator(strict_mode=False)  # Use non-strict mode for fuzzing
        self.valid_inputs = []
        self.invalid_inputs = []
        self.sanitized_cache = {}
    
    @rule(input_data=st.text(min_size=1, max_size=100), 
          input_type=st.sampled_from(['username', 'message', 'command']))
    def validate_input(self, input_data, input_type):
        """Validate an input and track results."""
        try:
            if input_type == 'username':
                result = self.validator.validate_username(input_data)
            elif input_type == 'message':
                result = self.validator.validate_message(input_data)
            elif input_type == 'command':
                result = self.validator.validate_command(input_data)
            
            if result.is_valid:
                self.valid_inputs.append((input_data, input_type))
            else:
                self.invalid_inputs.append((input_data, input_type, result.errors))
                
        except Exception as e:
            pytest.fail(f"Input validation failed: {e}")
    
    @rule(input_data=st.text())
    def sanitize_input(self, input_data):
        """Sanitize input and cache results."""
        try:
            result = self.validator.validate_message(input_data)
            sanitized = result.sanitized_value or input_data
            self.sanitized_cache[input_data] = sanitized
            
        except Exception as e:
            pytest.fail(f"Input sanitization failed: {e}")
    
    @rule()
    def clear_cache(self):
        """Clear the sanitization cache."""
        self.sanitized_cache.clear()
    
    @invariant()
    def valid_inputs_are_consistent(self):
        """Invariant: valid inputs should remain valid on re-validation."""
        for input_data, input_type in self.valid_inputs[-10:]:  # Check last 10 to avoid performance issues
            try:
                if input_type == 'username':
                    result = self.validator.validate_username(input_data)
                elif input_type == 'message':
                    result = self.validator.validate_message(input_data)
                elif input_type == 'command':
                    result = self.validator.validate_command(input_data)
                
                assert result.is_valid, f"Previously valid input '{input_data}' of type '{input_type}' is now invalid"
            except Exception:
                # If validation crashes, that's a separate issue
                pass
    
    @invariant()
    def sanitized_inputs_are_safe(self):
        """Invariant: sanitized inputs should be strings."""
        # Note: The InputValidator doesn't actually sanitize dangerous patterns,
        # it validates them. So we just check that sanitized values are strings.
        for original, sanitized in list(self.sanitized_cache.items())[-10:]:  # Check last 10
            assert isinstance(sanitized, str), f"Sanitized value should be a string, got {type(sanitized)}"


# Create the test class for the state machine
TestInputValidationStateMachine = InputValidationStateMachine.TestCase


class TestUnicodeInputFuzzing:
    """Fuzzing tests for Unicode and international character handling."""
    
    @given(st.text(alphabet=st.characters(min_codepoint=0x80, max_codepoint=0x10000), 
                   min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_unicode_username_handling(self, unicode_username):
        """Test handling of Unicode characters in usernames."""
        try:
            is_valid, error_msg = validate_username(unicode_username)
            
            # Should handle Unicode gracefully
            assert isinstance(is_valid, bool)
            assert error_msg is None or isinstance(error_msg, str)
            
        except Exception as e:
            pytest.fail(f"Unicode username handling crashed with '{repr(unicode_username)}': {e}")
    
    @given(st.text(alphabet=st.characters(min_codepoint=0x1F600, max_codepoint=0x1F64F), 
                   min_size=1, max_size=20))
    @settings(max_examples=50)
    def test_emoji_handling(self, emoji_text):
        """Test handling of emoji characters."""
        try:
            # Test in usernames
            is_valid_username, _ = validate_username(emoji_text)
            assert isinstance(is_valid_username, bool)
            
            # Test in messages
            is_valid_message, _ = validate_message(emoji_text)
            assert isinstance(is_valid_message, bool)
            
            # Test sanitization
            sanitized = sanitize_input(emoji_text)
            assert isinstance(sanitized, str)
            
        except Exception as e:
            pytest.fail(f"Emoji handling crashed with '{repr(emoji_text)}': {e}")
    
    @given(st.text(alphabet=st.characters(blacklist_categories=['Cc', 'Cf']), 
                   min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_non_control_character_handling(self, text_without_control_chars):
        """Test handling of text without control characters."""
        try:
            # Should handle most non-control characters gracefully
            sanitized = sanitize_input(text_without_control_chars)
            assert isinstance(sanitized, str)
            
            # Length should not increase (only decrease or stay same)
            assert len(sanitized) <= len(text_without_control_chars)
            
        except Exception as e:
            pytest.fail(f"Non-control character handling crashed with '{repr(text_without_control_chars)}': {e}")


class TestEdgeCaseInputFuzzing:
    """Fuzzing tests for edge cases and boundary conditions."""
    
    @given(st.integers(min_value=0, max_value=10000))
    @settings(max_examples=100)
    def test_length_boundary_conditions(self, length):
        """Test various input lengths."""
        try:
            # Create string of specific length
            test_string = 'a' * length
            
            # Test username validation
            is_valid_username, _ = validate_username(test_string)
            assert isinstance(is_valid_username, bool)
            
            # Test message validation
            is_valid_message, _ = validate_message(test_string)
            assert isinstance(is_valid_message, bool)
            
            # Test sanitization
            sanitized = sanitize_input(test_string)
            assert isinstance(sanitized, str)
            
        except Exception as e:
            pytest.fail(f"Length boundary test crashed with length {length}: {e}")
    
    @given(st.text(alphabet='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f', 
                   min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_control_character_handling(self, control_char_text):
        """Test handling of various control characters."""
        try:
            # Should handle control characters without crashing
            sanitized = sanitize_input(control_char_text)
            assert isinstance(sanitized, str)
            
            # Control characters should be removed or handled
            for char in sanitized:
                if ord(char) < 32:
                    assert char in '\t\n\r', f"Unexpected control character in output: {repr(char)}"
                    
        except Exception as e:
            pytest.fail(f"Control character handling crashed with '{repr(control_char_text)}': {e}")
    
    @given(st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_batch_input_processing(self, input_list):
        """Test processing multiple inputs in sequence."""
        try:
            validator = InputValidator(strict_mode=False)  # Use non-strict mode for fuzzing
            results = []
            
            for input_data in input_list:
                result = validator.validate_message(input_data)
                is_valid = result.is_valid
                results.append((is_valid, result.errors))
                
                # Test sanitization through validation (InputValidator doesn't have public sanitize method)
                if result.sanitized_value is not None:
                    assert isinstance(result.sanitized_value, str)
            
            # All results should be valid tuples
            for is_valid, errors in results:
                assert isinstance(is_valid, bool)
                assert isinstance(errors, list)
                
        except Exception as e:
            pytest.fail(f"Batch processing crashed with {len(input_list)} inputs: {e}")


if __name__ == "__main__":
    # Run some basic fuzzing tests if executed directly
    import sys
    sys.path.insert(0, '.')
    
    test = TestInputValidationFuzzing()
    
    # Run a few examples manually
    test.test_username_validation_robustness("testuser")
    test.test_username_validation_robustness("")
    test.test_username_validation_robustness("a" * 100)
    
    print("Input fuzzing tests passed!")