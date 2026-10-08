-- ============================================================
--  STM SuperAttach
--  Version : 01
--  Author  : javibravovfx
--  License : MIT
-- ------------------------------------------------------------
--  DESCRIPTION
--    Attaches all selected objects into one or more meshes,
--    handling materials correctly regardless of count.
--    Based on Quick Attach v1.82 by Morozov Anton, extended
--    with a bucket-by-material strategy: objects are grouped
--    into buckets of up to 1000 unique materials each, and
--    each bucket produces one output mesh. This respects the
--    3ds Max MultiMaterial 1000-slot hard limit without losing
--    or corrupting any material.
--
--  FEATURES
--    - Supports Editable Poly, Editable Mesh, and Splines.
--    - Batch processing (configurable objects per part) with
--      progress bar and Escape-to-abort support.
--    - Buckets objects by unique material count so no output
--      mesh ever exceeds 1000 MultiMaterial slots.
--    - If total unique materials <= 1000: produces one mesh.
--    - If total unique materials > 1000: produces N meshes,
--      each with up to 1000 materials, and reports the count.
--    - "Divide by Material" mode: one mesh per unique material.
--    - Output placed in source layer or a new layer (optional).
--    - Live selection counter via callbacks.
--    - Normals utilities: Specify and Reset via Edit Normals.
--    - Full Undo support.
--
--  INSTALLATION
--    Drag-and-drop this file onto the 3ds Max viewport, or
--    run it via MAXScript > Run Script.
--    The floating dialog opens automatically.
--
--  USAGE
--    1. Select the objects you want to attach.
--    2. Choose output type: Editable Poly, Mesh, or Splines.
--    3. Choose attach method: all in one mesh, or divide by Material.
--    4. Adjust "Objects in one part" if memory is limited.
--    5. Optionally check "Create in new layer".
--    6. Click Attach.
--    7. Press Escape at any time to abort the operation.
--
--  TESTED ON  3ds Max 2022 - 2026
-- ============================================================

try destroyDialog Quick_Attach catch()

-- Remove any previous selection callback registered by this script
callbacks.removeScripts id:#stm_superattach

STM_SA_seq = 300

-- ------------------------------------------------------------------
-- Group objects into buckets of up to maxSlots unique materials each.
-- Returns array of arrays (buckets).
-- ------------------------------------------------------------------
fn STM_SA_bucketByMaterial arr maxSlots =
(
	local buckets    = #()
	local bucketMats = #()

	for obj in arr do
	(
		local m = obj.material
		local placed = false

		for b = 1 to buckets.count while not placed do
		(
			local alreadyIn = false
			for k = 1 to bucketMats[b].count while not alreadyIn do
				if bucketMats[b][k] == m do alreadyIn = true

			local wouldAdd = if alreadyIn then 0 else 1

			if (bucketMats[b].count + wouldAdd) <= maxSlots do
			(
				append buckets[b] obj
				if not alreadyIn do append bucketMats[b] m
				placed = true
			)
		)

		if not placed do
		(
			append buckets   #(obj)
			append bucketMats #(m)
		)
	)
	buckets
)

-- ------------------------------------------------------------------
-- Move obj to layer by name. Creates the layer if it doesn't exist.
-- ------------------------------------------------------------------
fn STM_SA_moveToLayer obj layerName =
(
	local lyr = LayerManager.getLayerFromName layerName
	if lyr == undefined do lyr = LayerManager.newLayer()
	if lyr != undefined do
	(
		lyr.setName layerName
		lyr.addNode obj
	)
)

-- ------------------------------------------------------------------
-- Attach one bucket of objects into a single mesh.
-- ------------------------------------------------------------------
fn STM_SA_attachBucket arr seqVal baseName srcLayer =
(
	if arr.count == 0 do return undefined

	if arr.count == 1 do
	(
		local solo = arr[1]
		if Quick_Attach.rdo1.state == 1 do convertTo solo Editable_Poly
		if Quick_Attach.rdo1.state == 2 do convertTo solo Editable_Mesh
		solo.name = baseName
		return solo
	)

	local b = undefined
	if Quick_Attach.rdo1.state == 3 then
		b = splineShape()
	else
		b = Editable_Mesh()
	if Quick_Attach.rdo1.state == 1 do convertTo b Editable_Poly
	b.name = baseName

	local count = 0
	for i = 1 to arr.count do
	(
		if not IsValidNode arr[i] do continue

		count += 1
		if count >= seqVal do
		(
			count = 0
			local pct = 1000 / (arr.count * 10 / i)
			Quick_Attach.pb1.value = pct
			gc()
			if (((maxVersion())[1] / 1000) >= 13) do windows.processPostedMessages()
			if (keyboard.EscPressed) and (queryBox "Do you want to abort Quick_Attach?") then return b
		)

		if (Quick_Attach.rdo1.state == 3) and (SuperClassOf arr[i] == Shape) do
		(
			convertTo arr[i] SplineShape
			addandweld b arr[i] -1
			continue
		)

		if SuperClassOf arr[i] == GeometryClass then
		(
			case Quick_Attach.rdo1.state of
			(
				1: polyop.attach b arr[i]
				2: meshop.attach b arr[i] attachMat:#IDToMat condenseMat:true deleteSourceNode:true
			)
		)
		else
		(
			if (Quick_Attach.chk1.checked) and (SuperClassOf arr[i] == Shape) and
			   (arr[i].render_renderable) do
			(
				arr[i].render_displayRenderMesh = true
				case Quick_Attach.rdo1.state of
				(
					1: polyop.attach b arr[i]
					2: meshop.attach b arr[i] attachMat:#IDToMat condenseMat:true deleteSourceNode:true
				)
			)
		)
	)

	local mymax = b.max
	local mymin = b.min
	b.pivot = [(mymax.x+mymin.x)/2, (mymax.y+mymin.y)/2, (mymax.z+mymin.z)/2]

	-- Layer placement
	if Quick_Attach.chk_newlayer.checked then
		STM_SA_moveToLayer b baseName
	else if srcLayer != undefined do
		srcLayer.addNode b

	b
)

-- ------------------------------------------------------------------
-- Main attach
-- ------------------------------------------------------------------
fn STM_SA_attachAll =
(
	if selection.count == 0 do ( messagebox ("Select objects first"); return false )

	local seqVal   = Quick_Attach.spn1.value
	local allObjs  = (selection as array)
	local baseName = allObjs[1].name

	-- Capture source layer of first object before clearing selection
	local srcLayer = undefined
	local srcLayerName = allObjs[1].layer.name
	srcLayer = LayerManager.getLayerFromName srcLayerName

	clearSelection()

	case Quick_Attach.attach_methods.state of
	(
		1: (
			local buckets = STM_SA_bucketByMaterial allObjs 1000
			local results = #()

			for b = 1 to buckets.count do
			(
				local name = if buckets.count == 1 then baseName \
				             else (baseName + "_part" + b as string)
				local res = STM_SA_attachBucket buckets[b] seqVal name srcLayer
				if res != undefined do append results res
			)

			Quick_Attach.pb1.value = 0

			if results.count == 1 then
			(
				select results[1]
				messagebox ("Attach done.")
			)
			else
			(
				for r in results do selectMore r
				messagebox ("Total unique materials exceeded 1000.\n" + \
				            results.count as string + " meshes created, each with up to 1000 materials.")
			)
		)

		2: (
			local mtlArr    = #()
			local ObjByMats = #()
			for obj in allObjs do
			(
				local i = findItem mtlArr obj.material
				if i == 0 do
				(
					append mtlArr obj.material
					append ObjByMats #(obj)
				)
				if i > 0 do append ObjByMats[i] obj
			)
			for i = 1 to ObjByMats.count do
			(
				local name = if mtlArr[i] != undefined then mtlArr[i].name \
				             else (baseName + "_" + i as string)
				STM_SA_attachBucket ObjByMats[i] seqVal name srcLayer
			)
			Quick_Attach.pb1.value = 0
			messagebox ("Attach done. Created " + ObjByMats.count as string + " objects.")
		)
	)

	free allObjs
)

-- ------------------------------------------------------------------
-- UI
-- ------------------------------------------------------------------
rollout Quick_Attach "STM SuperAttach v1.0" width:176 height:530
(
	label        'lbl1'            "Selected objects:"          pos:[8,8]     width:160 height:16                                                     align:#left
	label        'lbl2'            "0"                          pos:[8,24]    width:160 height:16                                                     align:#left
	radiobuttons 'rdo1'            "Create:"    pos:[24,44]     width:104     height:62 labels:#("Editable Poly", "Editable Mesh", "Splines / Shapes") columns:1 align:#left
	radiobuttons 'attach_methods'  "Attach method:" pos:[24,112] width:109    height:46 labels:#("all in one mesh", "divide by Material") columns:1   align:#left
	checkbox     'chk1'            "include renderable shapes"  pos:[8,165]   width:160 height:18 checked:false                                       align:#left
	checkbox     'chk_newlayer'    "Create in new layer"        pos:[8,186]   width:160 height:18 checked:false                                       align:#left
	spinner      'spn1'            ""                           pos:[6,213]   width:62  height:16 enabled:true range:[1,10000,300] type:#integer       align:#left
	label        'lbl11'           "Objects in one part"        pos:[72,213]  width:101 height:17                                                     align:#left
	label        'lbl19'           "(reduce if not enough memory)" pos:[8,230] width:160 height:17                                                    align:#left
	button       'bt_attach'       "Attach"                     pos:[39,256]  width:96  height:29 toolTip:"Combine selected objects"                  align:#left
	label        'lbl9'            "To abort - hold Escape. Cannot undo if selected more than objects in one part" pos:[8,292] width:162 height:54    align:#left
	GroupBox     'grp1'            "Normals"                    pos:[10,354]  width:158 height:119                                                    align:#left
	button       'bt_specify'      "Specify"                    pos:[43,376]  width:96  height:19 toolTip:"Edit normals - Specify"                    align:#left
	button       'bt_reset'        "Reset"                      pos:[43,410]  width:96  height:19 toolTip:"Reset normals"                             align:#left
	label        'lbl10'           "Object to be converted to Editable Poly" pos:[17,435] width:128 height:32                                         align:#left
	progressBar  'pb1'             ""                           pos:[8,516]   width:163 height:8  color:(color 220 40 40)                             align:#left

	on Quick_Attach open do
	(
		spn1.value = STM_SA_seq
		-- Register selection-change callback to keep counter live
		callbacks.addScript #selectionSetChanged \
			"if (Quick_Attach != undefined) do Quick_Attach.lbl2.caption = (getCurrentSelection()).count as string" \
			id:#stm_superattach
		lbl2.caption = (getCurrentSelection()).count as string
	)

	on Quick_Attach close do
	(
		-- Clean up callback when dialog is closed
		callbacks.removeScripts id:#stm_superattach
	)

	on bt_attach pressed do
	(
		undo "STM_SuperAttach" on ( STM_SA_attachAll() )
		lbl2.caption = (getCurrentSelection()).count as string
	)

	on bt_specify pressed do
	(
		if selection.count == 1 then
		(
			local b = selection[1]
			if (SuperClassOf b == GeometryClass) then
			(
				undo "STM_SuperAttach" on
				(
					if (ClassOf b != Editable_Poly) do convertTo b Editable_Poly
					modPanel.addModToSelection (Edit_Normals ()) ui:on
					local normcount = b.edit_normals.EditNormalsMod.GetNumNormals()
					b.edit_normals.EditNormalsMod.SetSelection #{1..normcount}
					b.edit_normals.EditNormalsMod.Specify()
					subobjectLevel = 0
					maxOps.CollapseNodeTo $ 1 true
				)
			) else messagebox ("Selection is not geometry")
		) else messagebox ("Please select 1 object")
	)

	on bt_reset pressed do
	(
		if selection.count == 1 then
		(
			local b = selection[1]
			if (SuperClassOf b == GeometryClass) then
			(
				undo "STM_SuperAttach" on
				(
					if (ClassOf b != Editable_Poly) do convertTo b Editable_Poly
					modPanel.addModToSelection (Edit_Normals ()) ui:on
					local normcount = b.edit_normals.EditNormalsMod.GetNumNormals()
					b.edit_normals.EditNormalsMod.SetSelection #{1..normcount}
					b.edit_normals.EditNormalsMod.Reset()
					subobjectLevel = 0
					maxOps.CollapseNodeTo $ 1 true
				)
			) else messagebox ("Selection is not geometry")
		) else messagebox ("Please select 1 object")
	)

	on rdo1 changed stat do
	(
		if rdo1.state == 3 then ( attach_methods.enabled = false; chk1.enabled = false )
		else ( attach_methods.enabled = true; chk1.enabled = true )
	)
)

createDialog Quick_Attach
Quick_Attach.lbl2.caption = (getCurrentSelection()).count as string
