/*
Script Name:    STM_Overscan.ms
Version:        v1.0.0
Description:
    Overscan tool — adds overscan pixels around the current render resolution.
    Inspired by Overscan 0.26 by Martin Breidt (martin@breidt.net)
    http://scripts.breidt.net
    Llamado via rt.fileIn() desde StudioToolbar-max.
*/

try(destroyDialog _roOverScan)catch()

rollout _roOverScan "STM Overscan" (
    groupbox _gbRnNfo "Render Info" pos:[5,5] width:185 height:60
        label _lblOldSz "" pos:[15,20] width:165 height:18
        label _lblOldAsp "" pos:[15,40] width:165 height:18
    
    groupbox _gbNewSz "New Settings" pos:[5,70] width:185 height:210
        label _lblX "Width" pos:[15,90] width:40 height:18
        spinner _spnX "" pos:[55,90] width:70 height:16 range:[-32000,32000,renderWidth] type:#integer
        checkbox _cbXRel "Rel" pos:[135,90] width:40 height:18 tooltip:"Relative to current width"
        
        label _lblY "Height" pos:[15,115] width:40 height:18
        spinner _spnY "" pos:[55,115] width:70 height:16 range:[-32000,32000,renderHeight] type:#integer
        checkbox _cbYRel "Rel" pos:[135,115] width:40 height:18 tooltip:"Relative to current height"
        
        label _lblAsp "Aspect" pos:[15,140] width:40 height:18
        spinner _spnAsp "" pos:[55,140] width:70 height:16 range:[0.001,100, (renderWidth as float / renderHeight)]
        checkbutton _cbLock "L" pos:[135,140] width:40 height:18 highlightcolor:red tooltip:"Lock aspect ratio"
        
        checkbox _chkKeepCam "Keep original camera" pos:[15,170] checked:true
        checkbox _chkAnim "Keyframe FOV/Focal Length" pos:[15,190] checked:false
        button _btnResetRes "Current Res" pos:[15,215] width:165 height:22
        button _btnGo "OVERSCAN" pos:[15,245] width:165 height:26 style:#struct_toolbar_buttons

    fn updateInfo = (
        _lblOldSz.text = "Current Res: " + renderWidth as string + " x " + renderHeight as string
        _lblOldAsp.text = "Current Aspect: " + (( (renderWidth as float / renderHeight)*1000 as integer)/1000.0) as string
    )

    on _roOverScan open do updateInfo()

    on _btnResetRes pressed do (
        _cbXRel.checked = _cbYRel.checked = false
        _spnX.value = renderWidth; _spnY.value = renderHeight
        _spnAsp.value = (renderWidth as float / renderHeight)
        updateInfo()
    )

    on _cbXRel changed state do (
        if state then _spnX.value = 0 else _spnX.value = renderWidth
    )
    on _cbYRel changed state do (
        if state then _spnY.value = 0 else _spnY.value = renderHeight
    )

    on _spnX changed val do if _cbLock.state and not _cbXRel.checked and not _cbYRel.checked do _spnY.value = val / _spnAsp.value
    on _spnY changed val do if _cbLock.state and not _cbXRel.checked and not _cbYRel.checked do _spnX.value = val * _spnAsp.value

    on _btnGo pressed do (
        local targetCam = undefined
        if (isValidNode (viewport.getCamera())) then targetCam = viewport.getCamera()
        else if (selection.count == 1 and isKindOf selection[1] Camera) then targetCam = selection[1]
        
        if targetCam != undefined then (
            local xres = if _cbXRel.checked then (renderWidth + _spnX.value) else _spnX.value
            local yres = if _cbYRel.checked then (renderHeight + _spnY.value) else _spnY.value
            
            if (xres <= 0 or yres <= 0) then messageBox "Resolution must be greater than 0."
            else (
                local oldResX = renderWidth, oldResY = renderHeight
                if _chkKeepCam.checked then (
                    local newCam = copy targetCam
                    newCam.name = targetCam.name + "_overscan"
                    if (isValidNode (viewport.getCamera())) do viewport.setCamera newCam
                    targetCam = newCam
                )
                
                local factor = xres as float / oldResX
                undo "STM Overscan" on (
                    if isProperty targetCam #focalLength then targetCam.focalLength *= factor
                    else if isProperty targetCam #fov do targetCam.fov = 2 * atan(tan(targetCam.fov/2.0) * factor)
                    if isProperty targetCam #film_width_mm then targetCam.film_width_mm *= factor
                    else if isProperty targetCam #film_width do targetCam.film_width *= factor
                    
                    renderWidth = xres; renderHeight = yres
                )
                destroyDialog _roOverScan
            )
        ) else messageBox "Please select a camera or activate a Camera Viewport."
    )
)
createDialog _roOverScan width:195 height:285