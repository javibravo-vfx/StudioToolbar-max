/*
Script Name:    STM_RemoveBack.ms
Version:        v2.0.0
Description:
    Removes the background bitmaps from every viewport
    and switches them to Solid Color mode.
    Run via rt.fileIn() from StudioToolbar-max.
*/

fn STM_RemoveBack =
(
    local originalViewport = viewport.activeViewport

    for i = 1 to viewport.numViews do (
        viewport.activeViewport = i
        -- Turn off the background bitmap display
        viewport.DispBkgImage = false
        -- Switch to Solid Color mode
        viewport.EnableSolidBackgroundColorMode true
    )

    viewport.activeViewport = originalViewport
    redrawViews()
)

STM_RemoveBack()
