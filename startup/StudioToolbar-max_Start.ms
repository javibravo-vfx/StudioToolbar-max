-- ============================================================================
--  StudioToolbar-max_Start.ms
--  Launches Studio Toolbar for MAX every time 3ds Max starts.
-- ----------------------------------------------------------------------------
--  INSTALL (once per machine / per Max version)
--    Copy THIS file into one of the 3ds Max startup script folders:
--
--      Per user (no admin rights needed):
--        %LOCALAPPDATA%\Autodesk\3dsMax\<version> - 64bit\ENU\scripts\startup\
--
--      All users (needs admin rights):
--        C:\Program Files\Autodesk\3ds Max <version>\scripts\Startup\
--
--    Then restart 3ds Max.
--
--  CONFIG
--    TOOLBAR_PATH must point to StudioToolbar-max.py on your studio drive.
--    Change it if the toolbar does not live in T:\.studio-toolbar\max\
-- ============================================================================

(
    local TOOLBAR_PATH = @"T:\.studio-toolbar\max\StudioToolbar-max.py"

    if doesFileExist TOOLBAR_PATH then
        python.ExecuteFile TOOLBAR_PATH
    else
        format "[Studio Toolbar] Not started - file not found: %\n" TOOLBAR_PATH
)
