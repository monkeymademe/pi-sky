# Troubleshooting: Server Not Responding

## Step 1: Check Server Terminal

Look at the terminal where you're running `python3 flight_tracker_server.py`. 

When you run `python3 test_flights_api.py`, you should see in the server terminal:

```
📡📡📡 Flights API request received: /api/flights?limit=1
   Request method: GET
   Client: ('127.0.0.1', xxxxx)
   Parsed path: /api/flights, query: limit=1
```

**If you DON'T see these messages**, the request isn't reaching the handler. This means:
- The route isn't matching
- OR the server crashed
- OR you're hitting a different server instance

## Step 2: Verify Server Restart

**CRITICAL:** After code changes, you MUST restart the server:

1. **Stop the server** - Press Ctrl+C in the terminal
2. **Wait for it to fully stop** - Should return to command prompt
3. **Start it again:**
   ```bash
   python3 flight_tracker_server.py
   ```
4. **Wait for startup messages** - Should see "Server starting..." etc.

## Step 3: Test Basic Route

Try accessing a simple endpoint first:

```bash
curl "http://localhost:5050/"
```

Should return HTML (the main page).

## Step 4: Check if Route Exists

Check the route matching in `do_GET()`:

```python
elif self.path.startswith('/api/flights'):
    self.handle_flights_api()
```

The route should match `/api/flights?limit=1` because `startswith` checks the path before the `?`.

## Step 5: Check for Exceptions

If the server is crashing on the request, check the server terminal for Python tracebacks.

## Quick Fix

If nothing works, try this simple test:

1. **Stop server** (Ctrl+C)
2. **Edit `flight_tracker_server.py`** - Add this at the start of `handle_flights_api()`:
   ```python
   print("=" * 60)
   print("FLIGHTS API CALLED!")
   print("=" * 60)
   ```
3. **Restart server**
4. **Run test again**
5. **Check if you see "FLIGHTS API CALLED!" in server terminal**

If you see it, the route works but something in the handler is hanging.
If you DON'T see it, the route isn't matching.

