/*
Script Name:    STM_RemoveBack.ms
Version:        v2.0.0
Description:
    Remueve los bitmaps de background de todos los viewports
    y los pone en modo Solid Color.
    Llamado via rt.fileIn() desde StudioToolbar-max.
*/

fn STM_RemoveBack =
(
    local originalViewport = viewport.activeViewport

    for i = 1 to viewport.numViews do (
        viewport.activeViewport = i
        -- Desactivar display del bitmap de background
        viewport.DispBkgImage = false
        -- Activar modo Solid Color
        viewport.EnableSolidBackgroundColorMode true
    )

    viewport.activeViewport = originalViewport
    redrawViews()
)

STM_RemoveBack()
