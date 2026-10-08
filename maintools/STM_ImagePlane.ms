-- ============================================================
--  STM ImagePlane
--  Version : 02
--  Author  : javibravovfx
--  License : MIT
-- ------------------------------------------------------------
--  DESCRIPTION
--    Attaches a camera-aligned image plane to any 3ds Max
--    camera as a modifier. The plane is sized to match the
--    camera frustum at a given distance (Maya-style), lives on
--    a dedicated frozen layer (ImagePlanes), and is
--    non-renderable by default so it never appears in output.
--
--  FEATURES
--    - Works with Target, Free, VRay Physical, and other
--      cameras; uses a robust 4-fallback distance resolver.
--    - Lock Optical Size: keeps the apparent screen size
--      constant as you change the distance. When active,
--      X/Y offsets are also scaled proportionally so the
--      plane stays at the same screen position.
--    - Alpha-aware material setup (Mix map for opacity).
--    - Visibility toggle synced correctly on rollout reopen.
--    - Reset Offsets X/Y button.
--    - Export button: clones the plane to the active layer as
--      a fully independent, unfrozen, renderable object.
--
--  INSTALLATION
--    Drag-and-drop this file onto the 3ds Max viewport, or
--    run it via MAXScript > Run Script.
--    The floating dialog opens automatically.
--
--  USAGE
--    1. Select a camera.
--    2. Click CREATE IMAGE PLANE.
--    3. In the modifier panel, click SELECT IMAGE... to pick
--       a bitmap. The plane is created and positioned at the
--       camera's target distance.
--    4. Adjust Distance, Scale, Offset, and Opacity as needed.
--    5. EXPORT TO SCENE copies the plane to the active layer
--       as a free object (no longer tied to the modifier).
--    6. DELETE IMAGE PLANE removes the modifier and the plane.
--
--  TESTED ON  3ds Max 2022 - 2026
-- ============================================================

(
	-- --------------------------------------------------------
	-- 1. MODIFIER CUSTOM ATTRIBUTES
	-- --------------------------------------------------------
	local ipAttribs = attributes imagePlane_Props (
		parameters main rollout:params (
			pRefPlane type:#maxobject
			pScale    type:#float      default:100.0  ui:spnScale
			pOffsetX  type:#worldunits default:0      ui:spnOffsetX
			pOffsetY  type:#worldunits default:0      ui:spnOffsetY
			pOffsetZ  type:#worldunits default:100.0  ui:spnOffsetZ
			pOpacity  type:#float      default:100.0  ui:spnOpacity
			pLockOpt  type:#boolean    default:false  ui:chkLockOpt
		)

		rollout params "Image Plane Controls" (

			-- Returns the reference plane node (or undefined)
			fn getRP = (
				local md = custAttributes.getOwner this
				if (classof md.pRefPlane) == NodeTransformMonitor then md.pRefPlane.node else undefined
			)

			-- ------------------------------------------------
			-- Robust target-distance resolver.
			-- Handles: Target Camera, Free Camera, VRay
			-- Physical Camera (with/without target node), and
			-- any camera that exposes a focus/target property.
			-- ------------------------------------------------
			fn getCamTargetDist cam = (
				local d = undefined

				-- Priority 1: real target node (Target Cam, VRay Target, etc.)
				if isProperty cam #target and cam.target != undefined then
					d = distance cam cam.target

				-- Priority 2: read the parameter directly from baseObject
				if d == undefined or d == 0 then (
					local bo = cam.baseObject
					local propNames = #(#targetDistance, #target_distance, #focus_distance, #focusDistance, #tDist)

					for pn in propNames while (d == undefined or d <= 0) do (
						if isProperty bo pn then (
							local raw = getProperty bo pn
							if raw != undefined and (raw as float) > 0 then d = raw as float
						)
					)

					if d == undefined or d <= 0 then (
						for pn in propNames while (d == undefined or d <= 0) do (
							if isProperty cam pn then (
								local raw = getProperty cam pn
								if raw != undefined and (raw as float) > 0 then d = raw as float
							)
						)
					)
				)

				-- Priority 3: parameterBlock scan (world-unit safe)
				if d == undefined or d <= 0 then (
					try (
						local bo = cam.baseObject
						local pb = bo.parameterBlock
						if pb != undefined then (
							local nParams = pb.count
							for i = 1 to nParams while (d == undefined or d <= 0) do (
								local pName = pb.paramName i
								if (findString (toLower (pName as string)) "target") != undefined or \
								   (findString (toLower (pName as string)) "focus")  != undefined then (
									local v = pb[i]
									if v != undefined and (v as float) > 0 then d = v as float
								)
							)
						)
					) catch ()
				)

				-- Priority 4: unit conversion fallback
				if d == undefined or d <= 0 then (
					try (
						local rawDist = if isProperty cam.baseObject #targetDistance \
										then cam.baseObject.targetDistance \
										else if isProperty cam #targetDistance \
										then cam.targetDistance \
										else undefined

						if rawDist != undefined and rawDist > 0 then
							d = maxOps.unitsConvert rawDist #inches #current
					) catch ()
				)

				if d == undefined or d <= 0 then d = 100.0
				return (d as float)
			)

			-- ------------------------------------------------
			-- Central position function.
			-- Writes X/Y/Z in one coordsys parent assignment to
			-- avoid multiple viewport redraws per spinner event.
			--   local X = right
			--   local Y = up
			--   local Z = -forward  (negate: positive distance = in front)
			-- ------------------------------------------------
			fn applyPosition rp = (
				if isValidNode rp then (
					in coordsys parent rp.pos = [pOffsetX, pOffsetY, -pOffsetZ]
				)
			)

			-- ------------------------------------------------
			-- UI CONTROLS
			-- ------------------------------------------------
			checkbox chkVis  "Visible" checked:true align:#left
			button   btnLoad "SELECT IMAGE..." width:150 height:35 color:(color 255 200 100)

			group "Distance & Optical Lock" (
				spinner  spnOffsetZ     "Distance"          range:[-1e9,1e9,100] type:#worldunits
				button   btnResetDist   "RESET DISTANCE"    width:140 height:22
				button   btnRecalc      "RECALCULATE"       width:140 height:22
				button   btnResetOffsets "RESET OFFSETS X/Y" width:140 height:22
				checkbox chkLockOpt    "Lock Optical Size"
			)

			group "Transforms" (
				spinner spnScale   "Scale (%)"  range:[0.01,1e9,100]
				spinner spnOffsetX "Offset X"   range:[-1e9,1e9,0] type:#worldunits
				spinner spnOffsetY "Offset Y"   range:[-1e9,1e9,0] type:#worldunits
				spinner spnOpacity "Opacity (%)" range:[0,100,100]
			)

			button btnExport "EXPORT TO SCENE" width:160 height:30 color:(color 120 200 120)

			-- lastD: the Distance value from the previous spnOffsetZ event.
			-- Used by Lock Optical Size to compute the scale/offset ratio.
			local lastD = 100.0

			-- ------------------------------------------------
			-- Create or update the image plane for a camera
			-- ------------------------------------------------
			fn updateImagePlane cam = (
				local bmap = selectBitMap()
				if bmap == undefined then return false

				local tDist = getCamTargetDist cam

				-- Frustum-correct sizing (Maya-style)
				local aspect = renderWidth as float / renderHeight as float
				local w = 2.0 * tDist * tan(cam.fov / 2.0)
				local h = w / aspect

				local rp    = getRP()
				local isNew = (not isValidNode rp)

				if isNew then (
					rp = Plane length:h width:w lengthsegs:1 widthsegs:1 \
					           name:(uniquename (cam.name + "_ImagePlane"))
					rp.material         = Standardmaterial name:(uniquename "Mat_IP")
					rp.parent           = cam
					rp.renderable       = false
					rp.showFrozenInGray = false

					local layName = "ImagePlanes"
					local nLayer  = LayerManager.getLayerFromName layName
					if nLayer == undefined then nLayer = LayerManager.newLayerFromName layName
					nLayer.addNode rp
					nLayer.isFrozen = true

					local md = custAttributes.getOwner this
					md.pRefPlane = nodeTransformMonitor node:rp forwardTransformChangeMsgs:false
				)

				-- Material setup
				if rp.material.diffuseMap == undefined then rp.material.diffuseMap = Bitmaptexture()
				rp.material.diffuseMap.fileName = bmap.filename

				if bmap.hasAlpha then (
					rp.material.diffuseMap.monoOutput  = 1
					rp.material.diffuseMap.alphasource = 0
					rp.material.opacityMap = Mix color1:white map1:rp.material.diffuseMap color2:black
				)

				rp.material.selfIllumAmount = 100.0
				showTextureMap rp.material on

				-- Position at the correct frustum depth (new planes only)
				if isNew then (
					rp.transform = cam.transform
					spnOffsetZ.value = pOffsetZ = tDist
					spnOffsetX.value = pOffsetX = 0
					spnOffsetY.value = pOffsetY = 0
					lastD = tDist
					applyPosition rp
				)

				btnLoad.text = filenameFromPath bmap.filename
			)

			-- ------------------------------------------------
			-- EVENT HANDLERS
			-- ------------------------------------------------

			-- Sync all UI controls to the current node state on open
			on params open do (
				local rp = getRP()
				if isValidNode rp then (
					local camNodes = refs.dependentnodes (custAttributes.getOwner this)
					local cam = undefined
					for n in camNodes where (superClassOf n == camera) do cam = n

					if cam != undefined then (
						-- Read back position from local coords to restore spinners correctly
						in coordsys parent (
							spnOffsetX.value = pOffsetX = rp.pos.x
							spnOffsetY.value = pOffsetY = rp.pos.y
							spnOffsetZ.value = pOffsetZ = -(rp.pos.z)
						)
						lastD = pOffsetZ

						if rp.material.diffuseMap != undefined then
							btnLoad.text = filenameFromPath rp.material.diffuseMap.fileName
					)

					-- Sync visibility checkbox with the actual node state
					chkVis.checked = not rp.isHidden
				)
			)

			on btnLoad pressed do (
				local camNodes = refs.dependentnodes (custAttributes.getOwner this)
				local cam = undefined
				for n in camNodes where (superClassOf n == camera) do cam = n

				if cam != undefined then updateImagePlane cam
			)

			on btnResetDist pressed do (
				local camNodes = refs.dependentnodes (custAttributes.getOwner this)
				local cam = undefined
				for n in camNodes where (superClassOf n == camera) do cam = n

				local rp = getRP()
				if cam != undefined and isValidNode rp then (
					local tDist = getCamTargetDist cam
					spnOffsetZ.value = pOffsetZ = tDist
					lastD = tDist
					applyPosition rp
				)
			)

			on btnRecalc pressed do (
				local camNodes = refs.dependentnodes (custAttributes.getOwner this)
				local cam = undefined
				for n in camNodes where (superClassOf n == camera) do cam = n

				local rp = getRP()
				if cam != undefined and isValidNode rp then (
					local tDist = spnOffsetZ.value

					local aspect = renderWidth as float / renderHeight as float
					local w = 2.0 * tDist * tan(cam.fov / 2.0)
					local h = w / aspect

					spnScale.value = pScale = 100.0
					rp.scale  = [1.0, 1.0, 1.0]
					rp.width  = w
					rp.length = h
				)
			)

			-- When distance changes:
			--   Always reposition keeping X/Y offsets (via applyPosition).
			--   If Lock Optical Size is ON:
			--     - Scale the plane so apparent screen size stays constant.
			--     - Scale X/Y offsets by the same ratio so the plane also
			--       stays at the same screen position (closer = smaller offset
			--       in world units, farther = larger offset in world units).
			--   ratio = newDist / oldDist  — the same linear perspective factor.
			--   All scale + position writes are batched inside disableSceneRedraw
			--   so the viewport only redraws once per spinner tick.
			on spnOffsetZ changed val do (
				local rp = getRP()
				if isValidNode rp and lastD != 0 then (
					disableSceneRedraw()
					if pLockOpt then (
						local ratio = val / lastD

						-- Keep apparent screen size constant
						local newScale = spnScale.value * ratio
						spnScale.value = newScale
						rp.scale = [newScale, newScale, newScale] / 100.0

						-- Keep screen position constant
						spnOffsetX.value = pOffsetX = pOffsetX * ratio
						spnOffsetY.value = pOffsetY = pOffsetY * ratio
					)

					lastD = val
					applyPosition rp
					enableSceneRedraw()
					redrawViews()
				)
			)

			on spnScale changed val do (
				local rp = getRP()
				if isValidNode rp then rp.scale = [val,val,val] / 100.0
			)

			on spnOffsetX changed val do (
				local rp = getRP()
				applyPosition rp
			)

			on spnOffsetY changed val do (
				local rp = getRP()
				applyPosition rp
			)

			on btnResetOffsets pressed do (
				local rp = getRP()
				if isValidNode rp then (
					spnOffsetX.value = pOffsetX = 0
					spnOffsetY.value = pOffsetY = 0
					applyPosition rp
				)
			)

			on spnOpacity changed val do (
				local rp = getRP()
				if isValidNode rp and rp.material != undefined then (
					if (isProperty rp.material #opacityMap) and rp.material.opacityMap != undefined then
						rp.material.opacityMap.mixAmount = 100.0 - val
					else
						rp.material.opacity = val
				)
			)

			on chkVis changed state do (
				local rp = getRP()
				if isValidNode rp then rp.isHidden = not state
			)

			-- Export: copies the plane to the active layer as a free,
			-- unfrozen, renderable object. The original stays intact.
			on btnExport pressed do (
				local rp = getRP()
				if not isValidNode rp then (
					messagebox "No active Image Plane found to export."
					return false
				)

				local exported            = copy rp
				exported.name             = uniquename (rp.name + "_exported")
				exported.parent           = undefined
				exported.isFrozen         = false
				exported.showFrozenInGray = false
				exported.renderable       = true

				local activeLayer = LayerManager.current
				activeLayer.addNode exported
				select exported

				messagebox ("\"" + exported.name + "\" exported to layer \"" + activeLayer.name + "\".")
			)
		)
	)

	-- --------------------------------------------------------
	-- 2. MAIN FLOATING DIALOG
	-- --------------------------------------------------------
	rollout rPipeIP "STM ImagePlane" width:200
	(
		button btnCreate "CREATE IMAGE PLANE" width:180 height:45
		button btnDelete "DELETE IMAGE PLANE" width:180 height:35

		on btnCreate pressed do (
			local cam = selection[1]
			if selection.count == 1 and (superClassOf cam) == camera then (
				local hasMod = false
				for m in cam.modifiers where m.name == "Image Plane" do hasMod = true

				if not hasMod then (
					local eMod = EmptyModifier name:"Image Plane"
					addModifier cam eMod
					custAttributes.add eMod ipAttribs
					max modify mode
				)
				else messagebox "This camera already has an Image Plane."
			)
			else messagebox "Please select a Camera object."
		)

		on btnDelete pressed do (
			local cam = selection[1]
			if selection.count == 1 and (superClassOf cam) == camera then (
				local rp           = undefined
				local modsToDelete = #()

				for m in cam.modifiers where m.name == "Image Plane" do (
					if (isProperty m #pRefPlane) and (classof m.pRefPlane) == NodeTransformMonitor then
						rp = m.pRefPlane.node
					append modsToDelete m
				)

				for m in modsToDelete do deleteModifier cam m
				if isValidNode rp then delete rp

				local nLayer = LayerManager.getLayerFromName "ImagePlanes"
				if nLayer != undefined then (
					local nodes; nLayer.nodes &nodes
					if nodes.count == 0 then LayerManager.deleteLayerByName "ImagePlanes"
				)
			)
			else messagebox "Select a camera to delete its Image Plane."
		)
	)

	createDialog rPipeIP
)
