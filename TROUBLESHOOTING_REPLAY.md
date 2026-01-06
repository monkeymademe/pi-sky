# Troubleshooting the Replay/History Page

## Issue: Page Shows "Loading flights..." But Nothing Happens

### Solution 1: Restart the Server

The new API endpoints require the server to be restarted:

1. **Stop the current server** (Ctrl+C in the terminal where it's running)

2. **Start it again:**
   ```bash
   python3 flight_tracker_server.py
   ```

3. **Refresh the browser page** (F5 or Ctrl+R)

### Solution 2: Check Browser Console

1. Open the browser console (F12 or right-click → Inspect → Console)
2. Look for error messages
3. The improved error handling should now show detailed error messages

### Solution 3: Test the API Directly

Test if the API is working:

```bash
curl "http://localhost:8080/api/flights?limit=5"
```

You should get JSON back. If you get HTML with "404 Not Found", the server needs to be restarted.

### Solution 4: Check Server Logs

When you request the page, you should see in the server terminal:
```
📡 Flights API request: /api/flights?limit=50
   Path parts: ['api', 'flights']
   Handling list flights route
   Query params: limit=50, active_only=False
   Returning X flights
```

If you don't see these messages, the route isn't matching (server needs restart).

### Solution 5: Verify Database

Check that flights exist:
```bash
python3 inspect_flight_db.py
```

If no flights are shown, the server needs to collect some data first.

## Common Issues

### "Network error: Could not connect to server"
- Server isn't running
- Wrong port (should be 8080 by default)
- Firewall blocking the connection

### "HTTP 503: Database not enabled"
- Check `config.json` has `"database": { "enabled": true }`
- Restart server after changing config

### "HTTP 404: Not Found"
- Server needs to be restarted to pick up new code
- Make sure you're accessing the correct URL

### "Invalid response format: flights is not an array"
- API returned unexpected format
- Check server logs for errors
- Check browser console for actual response

## Debug Steps

1. **Check server is running:**
   ```bash
   ps aux | grep flight_tracker_server
   ```

2. **Check server logs** for error messages

3. **Test API endpoint:**
   ```bash
   curl -v "http://localhost:8080/api/flights?limit=1"
   ```

4. **Check browser console** (F12) for JavaScript errors

5. **Check database has data:**
   ```bash
   python3 inspect_flight_db.py
   ```

## Still Not Working?

1. **Restart the server** - This is the most common fix
2. **Clear browser cache** - Ctrl+Shift+Delete
3. **Try incognito/private mode** - Rules out browser extensions
4. **Check server terminal** - Look for error messages
5. **Verify database file exists:**
   ```bash
   ls -la flights.db
   ```

## Expected Behavior

Once working, you should see:
- Flight list loads automatically
- Status bar shows flight count
- Each flight has a "Show Positions" button
- Clicking it loads and displays position data

If you see "Loading flights..." forever, check the browser console and server logs for errors.

