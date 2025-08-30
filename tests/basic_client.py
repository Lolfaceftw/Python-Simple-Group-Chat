import socket
import threading

def receive_messages(client_socket):
    """
    Handles receiving messages from the server in a separate thread.
    """
    while True:
        try:
            message = client_socket.recv(1024).decode('utf-8')
            if not message:
                print("Connection closed by the server.")
                break
            print(f"Received: {message}")
        except ConnectionResetError:
            print("Connection was forcibly closed by the remote host.")
            break
        except Exception as e:
            print(f"An error occurred while receiving messages: {e}")
            break

def main():
    """
    Main function to run the client.
    """
    # Prompt user for server IP and port
    host = input("Enter server IP address: ")
    port = int(input("Enter server port: "))

    # Create a client socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # Connect to the server
        client_socket.connect((host, port))
        print(f"Connected to server at {host}:{port}")
    except Exception as e:
        print(f"Failed to connect to the server: {e}")
        return

    # Start a thread to receive messages from the server
    receive_thread = threading.Thread(target=receive_messages, args=(client_socket,))
    receive_thread.daemon = True  # Allows main program to exit even if thread is running
    receive_thread.start()

    # Main loop to send messages
    try:
        while True:
            message_to_send = input()
            if message_to_send.lower() == 'exit':
                break
            client_socket.send(message_to_send.encode('utf-8'))
    except KeyboardInterrupt:
        print("\nClient is shutting down.")
    except Exception as e:
        print(f"An error occurred while sending messages: {e}")
    finally:
        # Close the client socket
        client_socket.close()

if __name__ == "__main__":
    main()