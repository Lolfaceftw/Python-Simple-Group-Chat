"""Simple test to check if the connection limiter works."""

from chat_app.server.security.connection_limiter import ConnectionLimiter

print("Testing ConnectionLimiter import...")
limiter = ConnectionLimiter()
print("ConnectionLimiter created successfully!")
print(f"Max connections per IP: {limiter.max_connections_per_ip}")