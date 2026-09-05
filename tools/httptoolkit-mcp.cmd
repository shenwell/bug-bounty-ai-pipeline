@echo off
rem Wrapper for Cursor MCP — path without spaces (Programs\HTTP Toolkit breaks spawn).
setlocal
set HTTPTOOLKIT_SERVER_REDIRECTED=1
"%LOCALAPPDATA%\httptoolkit-server\client\bin\httptoolkit-server.cmd" mcp %*
