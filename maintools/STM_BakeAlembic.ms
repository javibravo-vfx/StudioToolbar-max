/*
Script Name:    STM_BakeAlembic.ms
Version:        v2.0.0
Description:
    Bake Camera: copies any camera (an Alembic camera from Nuke, a camera with constraints,
    linked, on a path, a target camera...) into a native, editable camera with one key per frame:
    transform and FOV / focal length (FOV keys only when it changes).
    Bake to: Standard (Free Camera), Physical Camera or V-Ray Physical Camera (when installed).
    Select the camera (or the Alembic object / hierarchy that holds it) and press BAKE.
    Run via rt.fileIn() from StudioToolbar-max.

    How it reads the camera: Alembic objects only update at the scene time, not inside an
    "at time" context, so the script moves the time slider frame by frame, like a manual bake.
    The FOV is read from the viewport looking through the source camera (getViewFOV), which works
    for any camera type, also the Alembic ones whose parameters can't be seen or edited.
*/

try (destroyDialog STM_BakeCam_ro) catch ()
try (callbacks.removeScripts id:#STM_BakeCam) catch ()

global STM_BakeCam_ro
global STM_BakeCam_ini = (getDir #plugcfg) + "\\STM_BakeCamera.ini"

-- the camera to bake: the selected node or, for an Alembic hierarchy (container / xform), the first camera under it
fn STM_BakeCam_findCamera n =
(
    local found = undefined
    if n != undefined do
    (
        if superClassOf n == camera then found = n
        else for c in n.children while found == undefined do found = STM_BakeCam_findCamera c
    )
    found
)

fn STM_BakeCam_source =
(
    if selection.count != 1 then undefined else STM_BakeCam_findCamera selection[1]
)

-- the transform without scale (an Alembic from another app can bring a unit scale on the camera)
fn STM_BakeCam_noScale tm =
(
    matrix3 (normalize tm.row1) (normalize tm.row2) (normalize tm.row3) tm.row4
)

-- the target camera types this Max has: #(label, id)
fn STM_BakeCam_types =
(
    local t = #(#("Standard (Free Camera)", #free))
    if Physical_Camera != undefined do append t #("Physical Camera", #phys)
    if VRayPhysicalCamera != undefined do append t #("V-Ray Physical Camera", #vray)
    t
)

-- horizontal FOV (degrees) to the lens of the new camera
fn STM_BakeCam_setLens cam tid fov filmW =
(
    local f = filmW / 2.0 / (tan (fov / 2.0))
    case tid of
    (
        #free: cam.fov = fov
        #phys: (try (cam.focal_length_mm = f) catch (try (cam.specify_fov = true; cam.fov = fov) catch ()))
        #vray: (try (cam.focal_length = f) catch (try (cam.specify_fov = true; cam.fov = fov) catch ()))
    )
)

fn STM_BakeCam_create tid filmW =
(
    local cam = undefined
    case tid of
    (
        #phys: (
            cam = Physical_Camera targeted:false
            try (cam.specify_fov = false) catch ()
            try (cam.film_width_mm = filmW) catch (format "STM Bake Camera: could not set film_width_mm\n")
        )
        #vray: (
            cam = VRayPhysicalCamera targeted:false
            try (cam.specify_fov = false) catch ()
            try (cam.film_width = filmW) catch (format "STM Bake Camera: could not set film_width\n")
        )
        default: (
            cam = FreeCamera()
            try (cam.fovType = 1) catch () -- horizontal
        )
    )
    cam
)

-- samples the source frame by frame: #(#(time, transform, fov), ...); undefined if cancelled
fn STM_BakeCam_sample src s e noScale =
(
    local samples = #()
    local keepTime = sliderTime
    -- the active viewport looks through the source to read its FOV; it is restored after
    local vpCam = viewport.getCamera()
    local vpType = viewport.getType()
    local vpTM = viewport.getTM()
    local vpFov = getViewFOV()
    local cancelled = false
    viewport.setCamera src
    progressStart "Bake Camera: reading the source"
    try
    (
        for t = s to e while not cancelled do
        (
            sliderTime = t
            redrawViews()
            local tm = src.transform
            if noScale do tm = STM_BakeCam_noScale tm
            append samples #(t, tm, getViewFOV())
            if not (progressUpdate (100.0 * (t - s + 1) / (e - s + 1))) do cancelled = true
        )
    )
    catch (format "STM Bake Camera: %\n" (getCurrentException()))
    progressEnd()
    sliderTime = keepTime
    if vpCam != undefined then viewport.setCamera vpCam
    else
    (
        try (viewport.setType vpType) catch ()
        if vpType == #view_persp_user do (try (viewport.setTM vpTM; viewport.SetFOV vpFov) catch ())
    )
    redrawViews()
    if cancelled then undefined else samples
)

fn STM_BakeCam_bake src tid filmW s e noScale =
(
    local samples = STM_BakeCam_sample src s e noScale
    if samples == undefined or samples.count == 0 do return undefined
    local fovAnim = false
    for x in samples while not fovAnim where abs (x[3] - samples[1][3]) > 0.0001 do fovAnim = true
    local cam = undefined
    undo "Bake Camera" on
    (
        cam = STM_BakeCam_create tid filmW
        cam.name = uniqueName (src.name + "_BAKED")
        -- the lens of the first frame; keys only if it changes
        STM_BakeCam_setLens cam tid samples[1][3] filmW
        with animate on
        (
            for x in samples do at time x[1]
            (
                cam.transform = x[2]
                if fovAnim do STM_BakeCam_setLens cam tid x[3] filmW
            )
        )
    )
    #(cam, fovAnim, samples.count)
)

rollout STM_BakeCam_ro "STM Bake Camera" width:280
(
    local typeIds = #()

    label lblSrc "" align:#left width:256
    dropdownList ddType "Bake to" width:256
    spinner spFilm "Film width (mm) " range:[1, 200, 36] type:#float fieldwidth:60 align:#left \
        tooltip:"Physical / V-Ray: film width of the new camera. The FOV is kept; the focal length comes from it"
    group "Frames"
    (
        spinner spS "Start " range:[-100000, 100000, 0] type:#integer fieldwidth:60 across:2 align:#left
        spinner spE "End " range:[-100000, 100000, 100] type:#integer fieldwidth:60 align:#right
        button btnRange "Animation range" width:120 align:#left
    )
    checkbox chkScale "Remove scale from the transform" checked:true \
        tooltip:"An Alembic from Nuke can bring a scale on the camera node; the baked camera keeps position and rotation only"
    button btnBake "BAKE" width:256 height:30
    label lblInfo "" align:#left width:256 height:30

    fn updateSource =
    (
        local src = STM_BakeCam_source()
        if src == undefined then
        (
            lblSrc.text = "Select a camera (or the Alembic that holds it)"
            btnBake.enabled = false
        )
        else
        (
            lblSrc.text = "Source: " + src.name + "  (" + ((classOf src) as string) + ")"
            btnBake.enabled = true
            -- a physical source gives its film width
            local fw = try (src.film_width_mm) catch (try (src.film_width) catch (undefined))
            if classOf fw == Float and fw > 0 do spFilm.value = fw
        )
    )
    fn updateType = (spFilm.enabled = typeIds[ddType.selection] != #free)

    on STM_BakeCam_ro open do
    (
        local t = STM_BakeCam_types()
        ddType.items = for x in t collect x[1]
        typeIds = for x in t collect x[2]
        local last = getINISetting STM_BakeCam_ini "Bake" "Type"
        local i = findItem (for x in typeIds collect (x as string)) last
        ddType.selection = if i > 0 then i else 1
        spFilm.value = getRendApertureWidth()
        spS.value = animationRange.start.frame as integer
        spE.value = animationRange.end.frame as integer
        updateType()
        updateSource()
        callbacks.addScript #selectionSetChanged "try (STM_BakeCam_ro.updateSource()) catch ()" id:#STM_BakeCam
    )
    on STM_BakeCam_ro close do callbacks.removeScripts id:#STM_BakeCam
    on ddType selected i do
    (
        updateType()
        setINISetting STM_BakeCam_ini "Bake" "Type" (typeIds[i] as string)
    )
    on btnRange pressed do
    (
        spS.value = animationRange.start.frame as integer
        spE.value = animationRange.end.frame as integer
    )
    on btnBake pressed do
    (
        local src = STM_BakeCam_source()
        if src == undefined then messageBox "Select a camera (or the Alembic that holds it)" title:"Bake Camera"
        else if spE.value < spS.value then messageBox "End is before Start" title:"Bake Camera"
        else
        (
            local r = STM_BakeCam_bake src typeIds[ddType.selection] spFilm.value spS.value spE.value chkScale.checked
            if r == undefined then lblInfo.text = "Cancelled: nothing was created"
            else
            (
                lblInfo.text = r[1].name + ": " + (r[3] as string) + " frames, transform" + (if r[2] then " + FOV keys" else " keys (FOV constant)")
                format "STM Bake Camera: % from % (%), % frames\n" r[1].name src.name (classOf src) r[3]
                select r[1]
            )
        )
    )
)

createDialog STM_BakeCam_ro
