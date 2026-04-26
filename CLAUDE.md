# TaxFlow AI — Claude Code Instructions

## UI Issue Workflow

When the user reports a UI issue or asks you to check/fix the frontend visually:

1. **Do not ask the user to describe the problem.** Open the page yourself.
2. Ensure the frontend dev server is running (`cd frontend && npm run dev`). If it's not, start it in the background.
3. Use `playwright-cli` to inspect the page:
   - `playwright-cli open http://localhost:3000/<route>`
   - `playwright-cli snapshot` to read the DOM/accessibility tree
   - `playwright-cli screenshot` to see the page visually
4. Diagnose the issue from the snapshot/screenshot, find the component in code, and fix it.
5. After fixing, reload and re-snapshot to verify the fix.

### Auth0 Handling

The app uses Auth0 which blocks Playwright. Before inspecting the UI:

1. **Save** the current `frontend/.env.local` contents
2. **Swap to mock mode** by overwriting `.env.local` with:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:3000
   NEXT_PUBLIC_AUTH0_DOMAIN=
   NEXT_PUBLIC_AUTH0_CLIENT_ID=
   NEXT_PUBLIC_AUTH0_API_AUDIENCE=
   NEXT_PUBLIC_USE_MOCK_DATA=true
   ```
3. **Restart the dev server** (kill the existing one, run `cd frontend && npm run dev`)
4. Use `playwright-cli` to inspect and fix the UI
5. **Restore** the original `.env.local` contents and restart the dev server when done

This swap should be automatic and silent — do not ask the user for permission each time. Just do it, fix the UI, and restore.
