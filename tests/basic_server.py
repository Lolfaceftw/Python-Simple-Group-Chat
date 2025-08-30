import socket
import threading

# Connection Data
host = '0.0.0.0'  # Listen for connections on all available network interfaces.
port = 55555        # Port to listen on (non-privileged ports are > 1023)

# Starting Server
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((host, port))
server.listen()

# Lists For Clients and Their Nicknames
clients = []
nicknames = []

# Sending Messages To All Connected Clients
def broadcast(message, _client=None):
    for client in clients:
        # Send to all clients except the one specified (optional)
        if client != _client:
            try:
                client.send(message)
            except:
                # Handle broken connections
                close_connection(client)


# Close a client connection
def close_connection(client):
    if client in clients:
        index = clients.index(client)
        clients.remove(client)
        client.close()
        nickname = nicknames.pop(index)
        print(f'{nickname} has disconnected.')
        broadcast(f'{nickname} left!'.encode('ascii'))

# Handling Messages From Clients
def handle(client):
    while True:
        try:
            # Broadcasting Messages
            message = client.recv(1024)
            if not message:
                # Client disconnected
                close_connection(client)
                break

            decoded_message = message.decode('ascii')
            index = clients.index(client)
            nickname = nicknames[index]

            if decoded_message.startswith('NICK'):
                new_nickname = decoded_message.split(' ')[1].strip()
                nicknames[index] = new_nickname
                broadcast(f'{nickname} is now known as {new_nickname}'.encode('ascii'))
                print(f'{nickname} changed nick to {new_nickname}')
            elif decoded_message.lower() == 'bye':
                close_connection(client)
                break
            else:
                broadcast(f'{nickname}: {decoded_message}'.encode('ascii'))

        except (ConnectionResetError, ConnectionAbortedError):
            # Removing And Closing Clients on abrupt disconnect
            close_connection(client)
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            close_connection(client)
            break


# Receiving / Listening Function
def receive():
    while True:
        try:
            # Accept Connection
            client, address = server.accept()
            print(f"Connected with {str(address)}")

            # Request And Store Nickname
            client.send('NICK'.encode('ascii'))
            nickname = client.recv(1024).decode('ascii').strip()

            # If client disconnects before sending a nickname, nickname will be empty
            if not nickname:
                print(f"Connection from {address} dropped before sending nickname.")
                client.close()
                continue # Go to the next iteration of the loop

            nicknames.append(nickname)
            clients.append(client)

            # Print And Broadcast Nickname
            print(f"Nickname is {nickname}")
            broadcast(f"{nickname} joined!".encode('ascii'))
            client.send('Connected to server!'.encode('ascii'))

            # Start Handling Thread For Client
            thread = threading.Thread(target=handle, args=(client,))
            thread.start()
        except KeyboardInterrupt:
            print(f"Exiting...")
        except Exception as e:
            print(f"An error occurred during client connection: {e}")


print("Server is listening...")
receive()