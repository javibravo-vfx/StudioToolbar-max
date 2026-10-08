(
    if selection.count != 1 then
    (
        messageBox "Select the Alembic object (camera)"
        return false
    )

    local src = selection[1]
    format "SOURCE: % (Class: %)\n" src.name (classof src)

    local cam = FreeCamera()
    cam.name = uniqueName (src.name + "_BAKED")

    local startFrame = animationRange.start
    local endFrame   = animationRange.end

    with animate on
    (
        for t = startFrame to endFrame do
        (
            at time t
            (
                cam.transform = src.transform
                cam.fov = src.fov
            )
        )
    )

    messageBox "Camera created with baked TRANSFORM + FOV keys"
    select cam
)
