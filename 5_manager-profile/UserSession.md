# User Session Management (Cloak Browser)

This project uses the **Cloak Browser** with persistent `user_data_dir` to maintain authenticated LinkedIn sessions. This allows scraping scripts to remain logged in across different runs without re-authenticating.

## Session Storage
All sessions are stored in the `sessions/` directory:
`./sessions/{linkedin_user}/`

## Management Workflow

### 1. Initialization (Login)
To create or update a persistent session, use the sign-in script:
```bash
python linkedin_signin.py --user {username}
```
1. A browser window will open.
2. Navigate to [LinkedIn](https://www.linkedin.com) (if it doesn't open automatically) and log in.
3. Complete any necessary 2FA or CAPTCHAs.
4. Close the browser window and press **Enter** in the terminal to save your state.

### 2. Usage
When running scraping scripts (`scrape_linkedin_pictures.py` or `reprocess_not_found.py`), pass the same username you used during initialization:
```bash
python scrape_linkedin_pictures.py --scrape_method cloak_browser --linkedin_user {username}
```

### 3. Terminating (Logout & Cleanup)
To end the session and securely remove your data, use the sign-out script:
```bash
python linkedin_signout.py --user {username}
```
*   This automatically visits the LinkedIn logout page to invalidate the session on their servers, then deletes the local `sessions/{username}/` directory.

## Best Practices
*   **Keep Sessions Clean**: Do not browse other websites while logged in for scraping tasks to minimize the risk of being flagged by bot detection.
*   **One User, One Session**: Do not use the same `linkedin_user` session for multiple concurrent scraping processes, as this can trigger LinkedIn's multi-session or concurrency security alerts.
*   **Human Mimicry**: Always ensure human mimicry parameters (`--delay_min`, `--delay_max`, `--max_pages_per_hour`) are used to maintain session longevity.
