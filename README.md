# Selkies Remote Browser API

This project provides a simple API to dynamically manage and launch containerized web browsers, specifically based on the LinuxServer.io Chromium image. It's designed to create isolated, temporary browser sessions for users, with automatic cleanup for inactive sessions.

## 🚀 Quick Start

1.  **Clone the repository and navigate into the directory.**
2.  **Edit `docker-compose.yml`**: Update the following environment variables with your specific values.
      * `HOST_IP`: The public IP address or domain name of the host machine.
      * `HOST_PROFILES_PATH`: The absolute path on the host where user profiles will be stored. This directory should be created with appropriate permissions.
          * **Example**: `HOST_PROFILES_PATH=/opt/selkies_profiles`
3.  **Build and run the service** with Docker Compose:
    ```bash
    docker-compose up --build -d
    ```

-----

## ⚙️ Configuration

The application is configured through environment variables in the `docker-compose.yml` file and constants in `app.py`.

| Variable | Description | Default Value |
| :--- | :--- | :--- |
| `HOST_IP` | The public IP or domain of your server. This is used to construct the access URL. | `104.56.36.223` (Example) |
| `HOST_PROFILES_PATH` | The absolute path on your host machine for storing user profiles. | `/opt/not-kasm_profiles` (Example) |
| `SESSION_INACTIVITY_TIMEOUT` | The period after which an inactive container will be stopped. Defined in `app.py`. | `30 minutes` |

-----

## 🕹️ API Endpoints

The API runs on port **5000** and has the following endpoints:

### `POST /launch`

This endpoint is idempotent for a given user email. If a user already has an active session, it will not create a new container. Instead, it will return the details of the existing session and reset its inactivity timer. If no session is found, a new Chromium container is launched.

  * **Request Body (JSON)**:

    ```json
    {
        "email": "user@example.com",
        "name": "John Doe",
        "key": "skey@dc636923215643"
    }
    ```

      * **`email`** (required): Unique identifier for the user.
      * **`name`** (optional): User's name.
      * **`key`** (optional): An access key, with a default value provided.

  * **Example `curl` command**:

    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -d '{"email": "testuser@example.com", "name": "Test User"}' \
      http://localhost:5000/launch
    ```

-----

### `POST /heartbeat`

Updates the last active time for a container to prevent it from being stopped by the inactivity timeout.

  * **Request Body (JSON)**:

    ```json
    {
        "container_id": "a1b2c3d4e5f6..."
    }
    ```

  * **Example `curl` command**:

    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -d '{"container_id": "a1b2c3d4e5f6..."}' \
      http://localhost:5000/heartbeat
    ```

-----

### `GET /list`

Lists all active container sessions currently managed by the application.

  * **Example `curl` command**:
    ```bash
    curl http://localhost:5000/list
    ```

-----

### `POST /remove`

Stops and removes a specific container. Can be identified by either `container_id` or `email`.

  * **Request Body (JSON)**:

    ```json
    {
        "container_id": "a1b2c3d4e5f6"
    }
    ```

    OR

    ```json
    {
        "email": "user@example.com"
    }
    ```

  * **Example `curl` command (by container ID)**:

    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -d '{"container_id": "a1b2c3d4e5f6..."}' \
      http://localhost:5000/remove
    ```

  * **Example `curl` command (by email)**:

    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -d '{"email": "testuser@example.com"}' \
      http://localhost:5000/remove
    ```

-----

## 🛠️ Internal Mechanisms

  * **Inactivity Timeout**: Containers are automatically stopped after **30 minutes** of inactivity (no heartbeat). This value is defined by `SESSION_INACTIVITY_TIMEOUT = timedelta(minutes=30)` in `app.py`. To change this, you must edit the file and rebuild the Docker image.
  * **Heartbeat**: Clients should periodically send a `POST` request to the `/heartbeat` endpoint to reset the inactivity timer for their session.
  * **Cleanup**: A separate thread automatically removes containers that have stopped.
  * **Persistence**: User profiles are stored on the host machine in the directory specified by `HOST_PROFILES_PATH`, ensuring bookmarks and settings persist across sessions.
