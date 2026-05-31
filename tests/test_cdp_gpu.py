#!/usr/bin/env python3
"""Quick CDP test: connect to Chrome, query WebGL, print results.

Assumes Chrome is already running with devtools enabled on port 9222.
"""
import asyncio
import json
import aiohttp


async def query_webgl():
    """Connect to Chrome CDP and query WebGL info."""
    async with aiohttp.ClientSession() as session:
        # Get tab list
        async with session.get("http://localhost:9222/json") as resp:
            tabs = await resp.json()

        if not tabs:
            print("No tabs found")
            return

        ws_url = tabs[0].get("webSocketDebuggerUrl")
        if not ws_url:
            print("No WebSocket URL in tab")
            return

        print(f"Connecting to: {ws_url}")
        async with session.ws_connect(ws_url) as ws:
            msg = {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """
                    (function() {
                        var c = document.createElement('canvas');
                        var gl = c.getContext('webgl2') || c.getContext('webgl');
                        if (!gl) return JSON.stringify({error: 'no webgl context'});
                        var ext = gl.getExtension('WEBGL_debug_renderer_info');
                        return JSON.stringify({
                            vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
                            renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)
                        });
                    })()
                    """,
                    "returnByValue": True,
                },
            }
            await ws.send_json(msg)
            resp = await asyncio.wait_for(ws.receive_json(), timeout=10)

            result = resp.get("result", {}).get("result", {})
            if result.get("type") == "string":
                data = json.loads(result["value"])
                print(f"\n=== WebGL via CDP ===")
                print(f"  GL_VENDOR:   {data.get('vendor')}")
                print(f"  GL_RENDERER: {data.get('renderer')}")
                return data
            else:
                print(f"Unexpected result: {result}")
                return None


if __name__ == "__main__":
    asyncio.run(query_webgl())
