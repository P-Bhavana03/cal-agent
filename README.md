# Calendar Scheduling Assistant

This project is a calendar scheduling assistant that uses LangChain, Google's Gemini LLM, and function calling to help you create calendar events using natural language.

The project is structured into a FastAPI backend and a Streamlit frontend.

## Project Structure

- `backend/`: Contains the FastAPI server, LangChain agent, and tools to create, find, and update calendar events.
- `frontend/`: Contains the Streamlit chat application.
- `README.md`: This file.

## Features

- Create new calendar events using natural language.
- Find and update existing events (e.g., change time, add/remove attendees, update title).
- Automatically handles timezones based on your system's locale.

## Backend Setup

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```

2.  **Create and activate a virtual environment using `uv`:**
    ```bash
    uv venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```

3.  **Install the required dependencies:**
    ```bash
    uv pip install -r requirements.txt
    ```
    This will install FastAPI, LangChain, the Google libraries, and `tzlocal` for timezone handling.

4.  **Set up your environment variables:**
    - Create a `.env` file in the `backend` directory by copying the example:
      ```bash
      cp .env.example .env
      ```
    - Open the `.env` file and add your Google API Key:
      ```
      GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
      ```
      You can get a Google API key from the [Google Cloud Console](https://console.cloud.google.com/apis/credentials).

5.  **Set up Google Calendar API credentials:**
    
    This is the most critical part of the setup. Follow these steps carefully.

    a. **Enable the Google Calendar API:**
        - Go to the [Google Cloud API Library](https://console.cloud.google.com/apis/library).
        - Search for "Google Calendar API" and enable it for your project. This will grant permissions for `calendar.events`.

    b. **Configure the OAuth Consent Screen:**
        - Navigate to the [OAuth consent screen page](https://console.cloud.google.com/apis/credentials/consent).
        - Select **External** and click **Create**.
        - Provide an app name (e.g., "Calendar Scheduling Assistant"), your user support email, and your developer contact email.
        - Click **Save and Continue** through the "Scopes" and "Optional Info" sections.
        - Under **Test users**, add the Google account email you will be using to test the application.
        - Click **Save and Continue** and then **Back to Dashboard**.

    c. **Create Desktop App Credentials:**
        - Go back to the main [Credentials page](https://console.cloud.google.com/apis/credentials).
        - Click **+ CREATE CREDENTIALS** and select **OAuth client ID**.
        - In the **Application type** dropdown, you **must** select **Desktop app**.
        - Give the credential a name and click **Create**.

    d. **Download and Place the Credentials File:**
        - After creation, a dialog will appear. Click **DOWNLOAD JSON**.
        - Rename the downloaded file to exactly `credentials.json`.
        - Place the `credentials.json` file in the `backend` directory. It must be in the same directory as `main.py`.
    
    e. **Delete the old `token.json` file:**
       - If you have already run the application and it failed, you might have a `token.json` file in your `backend` directory. Please delete it before running the application again. **Since the API scopes have changed, you will need to do this to re-authenticate.**

6.  **Run the backend server:**
    ```bash
    uvicorn main:app --reload
    ```
    The server will be running at `http://127.0.0.1:8000`.

## Frontend Setup

1.  **Navigate to the frontend directory:**
    ```bash
    cd frontend
    ```

2.  **Create and activate a virtual environment using `uv`:**
    ```bash
    uv venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```

3.  **Install the required dependencies:**
    ```bash
    uv pip install -r requirements.txt
    ```

4.  **Run the Streamlit app:**
    ```bash
    streamlit run app.py
    ```
    The Streamlit application will open in your browser.

## How to Use

1.  Make sure both the backend and frontend servers are running.
2.  Open the Streamlit app in your browser.
3.  Because the API permissions have been updated, you **must re-authenticate**. Delete the `token.json` file from your `backend` directory if it exists.
4.  The first time you make a request, you will be prompted to authenticate with Google in your browser.
5.  Try out the new features!
    - **Create:** "Schedule a meeting for tomorrow at 10am with test@example.com about the project launch."
    - **Find:** "Find my meeting about the project launch."
    - **Update:** "Add user2@example.com to the project launch meeting." or "Change the project launch meeting to 11am."

The assistant will process your request, call the appropriate tools, and confirm the action has been completed. 