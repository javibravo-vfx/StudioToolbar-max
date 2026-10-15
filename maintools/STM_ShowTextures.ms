/*
Script Name:    STM_ShowTextures.ms
Version:        v2.0.0
Description:
    Toggles viewport textures ON/OFF for every material in the scene.
    Prefers the diffuse / base color map depending on the render engine.
    Supports: V-Ray, Arnold, FStorm, Corona, Octane, Standard, Physical.
    Run via rt.fileIn() from StudioToolbar-max.
*/

-- Initialise the state only the first time
if STM_ShowTextures_State == undefined then
    global STM_ShowTextures_State = false

-- Flip the state
STM_ShowTextures_State = not STM_ShowTextures_State

-- -------------------------------------------------------
-- Returns the "preferred" texmap (diffuse / base color)
-- for the material type. Falls back to the first
-- available texmap, or undefined if there is none.
-- -------------------------------------------------------
fn STM_GetPrimaryTexmap mat =
(
    local matClass = classof mat
    local tex = undefined

    -- VRay
    if matchPattern (matClass as string) pattern:"VRayMtl*" do (
        if mat.texmap_diffuse != undefined then tex = mat.texmap_diffuse
    )
    -- VRay 2-sided, VRayBlend, etc: fall back to the first submap
    if tex == undefined and matchPattern (matClass as string) pattern:"VRay*" do (
        if (getNumSubTexmaps mat) > 0 then tex = getSubTexmap mat 1
    )

    -- Arnold (aiStandardSurface)
    if tex == undefined and matchPattern (matClass as string) pattern:"aiStandard*" do (
        if mat.base_color != undefined then tex = mat.base_color
    )
    if tex == undefined and matchPattern (matClass as string) pattern:"ai*" do (
        if (getNumSubTexmaps mat) > 0 then tex = getSubTexmap mat 1
    )

    -- Corona
    if tex == undefined and matchPattern (matClass as string) pattern:"Corona*Mtl*" do (
        if mat.texmapDiffuse != undefined then tex = mat.texmapDiffuse
    )
    if tex == undefined and matchPattern (matClass as string) pattern:"CoronaMtl" do (
        if mat.texmapDiffuse != undefined then tex = mat.texmapDiffuse
    )

    -- FStorm
    if tex == undefined and (matClass as string) == "FStorm" do (
        if mat.diffuse_tex != undefined then tex = mat.diffuse_tex
    )

    -- Octane
    if tex == undefined and matchPattern (matClass as string) pattern:"Octane*" do (
        if (getNumSubTexmaps mat) > 0 then tex = getSubTexmap mat 1
    )

    -- Standard Max
    if tex == undefined and matClass == StandardMaterial do (
        if mat.diffuseMap != undefined then tex = mat.diffuseMap
    )

    -- Physical Material (PBR)
    if tex == undefined and matClass == PhysicalMaterial do (
        if mat.base_color_map != undefined then tex = mat.base_color_map
    )

    -- Fallback: first available submap
    if tex == undefined then (
        local numSubs = getNumSubTexmaps mat
        for i = 1 to numSubs while tex == undefined do (
            local sub = getSubTexmap mat i
            if sub != undefined then tex = sub
        )
    )

    tex
)

-- -------------------------------------------------------
-- Process one material: show its preferred texmap
-- -------------------------------------------------------
fn STM_ProcessMaterial mat newState =
(
    if mat == undefined then return()
    if classof mat == Multimaterial then (
        for i = 1 to mat.numsubs do
            STM_ProcessMaterial mat[i] newState
    ) else (
        local tex = STM_GetPrimaryTexmap mat
        if tex != undefined then
            showTexturemap mat tex newState
        else
            showTexturemap mat newState
    )
)

-- -------------------------------------------------------
-- Apply to every object in the scene
-- -------------------------------------------------------
setWaitCursor()
for obj in objects do (
    if obj.material != undefined then
        STM_ProcessMaterial obj.material STM_ShowTextures_State
)
redrawViews()
setArrowCursor()
