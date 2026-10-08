/*
================================================================================
  CarRig v1.7  -  Rig de autos con dummies para 3ds Max (MAXScript, gratis)
--------------------------------------------------------------------------------
  INTERFAZ: 1 RIG  ->  2 MANEJO  ->  3 SIMULAR   (+ Ajustes avanzados, plegado)
  Pasando el mouse sobre cada control aparece su explicacion.

  FLUJO
  1. MAXScript > Run Script > CarRig.ms
  2. (Opcional) selecciona el auto modelado: los dummies se crean a su tamano.
     CREAR RIG -> se crea el rig completo con dummies.
  3. Ubicar: los unicos dummies que se mueven son los *_POS (naranja) y el ROOT.
       - ROOT (amarillo, plano): en el piso, debajo del auto (mover/rotar).
         El texto FRENTE marca hacia donde mira el auto.
       - W??_POS: sobre cada rueda (FL FR RL RR).
       - W??_RADIO (circulo): Radius = radio de la cubierta.
       - BODY_POS: pivote de cabeceo/rolido de la carroceria.
     Con UBICAR DUMMIES activado, tus modelos se desvinculan para poder mover
     los dummies sin arrastrarlos. Al desactivarlo (o al bakear) se re-linkean.
  4. Linkear (a mano o con los botones):
       ruedas -> W??_SPIN | calipers -> W??_STEER | carroceria -> BODY_OFS
  5. Animar el ROOT (a mano o con una spline) y SIMULAR / BAKE.
     Cada bake relee la posicion de los *_POS y recalcula todo.

  Capas manuales: los dummies *_OFS (verdes) se animan a mano y el bake no los pisa.
  En el Modify del ROOT (animables): Spin mult, RPM extra, Steer mult/offset, Superficie.
================================================================================
*/

global CR_floater
global CR_roRig, CR_roDrive, CR_roSim, CR_roAdv
global CR_grounds = #()
global CR_currentRig = undefined
global CR_path = undefined
global CR_optKeys = #("autoSteer","maxSteer","smoothFr","anticip","ackermann","invSpin","invSteer","preset","amp","sizeMul","seedV","envelope","freq","damp","vib","pitchG","rollG","charSel","maxPitch","maxRoll")
global CR_labels = #("FL","FR","RL","RR")

struct CR_Opts
(
	autoSteer = true, maxSteer = 35.0, smoothFr = 4, anticip = 2, ackermann = true,
	invSpin = false, invSteer = false,
	preset = 3, amp = 1.0, sizeMul = 1.0, seedV = 1, envelope = true,
	freq = 1.4, damp = 0.35, vib = 0.15, pitchG = 2.5, rollG = 3.5, charSel = 2, maxPitch = 3.0, maxRoll = 4.0,
	groundNames = "-"
)

struct CR_RigData
(
	root, name = "", fwd = 2, wb = 1.0, track = 1.0,
	radii, rests, poss, sims, ofss, steers, spins, circles,
	bodyPos, bodySim, bodyOfs, bodyRest
)

-- ============================================================================
--  Atributos animables en el ROOT
-- ============================================================================
global CR_CADef = attributes CarRigControls
(
	parameters main rollout:params
	(
		spinMult    type:#float ui:spSpin   default:1.0
		extraRPM    type:#float ui:spRPM    default:0.0
		steerMult   type:#float ui:spSteerM default:1.0
		steerOffset type:#float ui:spSteerO default:0.0
		surfaceAmt  type:#float ui:spSurf   default:1.0
	)
	rollout params "Car Rig Controls"
	(
		spinner spSpin   "Spin mult:"    range:[-20,20,1]       type:#float
		spinner spRPM    "RPM extra:"    range:[-5000,5000,0]   type:#float
		spinner spSteerM "Steer mult:"   range:[-5,5,1]         type:#float
		spinner spSteerO "Steer offset:" range:[-60,60,0]       type:#float
		spinner spSurf   "Superficie:"   range:[0,10,1]         type:#float
		label lb1 "Animables. Re-bakear tras cambios."
	)
)

-- ============================================================================
--  Utilidades
-- ============================================================================
fn CR_unitsPerMeter =
(
	local perMeter = case units.SystemType of
	(
		#Inches: 39.3700787
		#Feet: 3.2808399
		#Miles: 0.000621371
		#Millimeters: 1000.0
		#Centimeters: 100.0
		#Meters: 1.0
		#Kilometers: 0.001
		default: 39.3700787
	)
	perMeter / units.SystemScale
)

fn CR_fwdVec i = case i of (1: [0,1,0]; 2: [0,-1,0]; 3: [1,0,0]; default: [-1,0,0])

fn CR_axisInfo v =
(
	if (abs v.x) > 0.5 then #(1, (if v.x > 0 then 1.0 else -1.0))
	else if (abs v.y) > 0.5 then #(2, (if v.y > 0 then 1.0 else -1.0))
	else #(3, (if v.z > 0 then 1.0 else -1.0))
)

-- tamano de caja en ejes locales: largo (frente), ancho (lateral), alto
fn CR_boxSize fwdV lenF lenL h = if (abs fwdV.y) > 0.5 then [lenL, lenF, h] else [lenF, lenL, h]

fn CR_setRot node idx val =
(
	local c = node.rotation.controller
	case idx of
	(
		1: c.X_Rotation = val
		2: c.Y_Rotation = val
		3: c.Z_Rotation = val
	)
)

fn CR_zeroRot node =
(
	local c = node.rotation.controller
	c.X_Rotation = 0.0
	c.Y_Rotation = 0.0
	c.Z_Rotation = 0.0
)

fn CR_localPos node =
(
	local c = node.pos.controller
	[c.X_Position, c.Y_Position, c.Z_Position]
)

fn CR_linearize node posIdx rotIdxs =
(
	if posIdx != 0 do node.pos.controller[posIdx].controller = Linear_Float()
	for r in rotIdxs do node.rotation.controller[r].controller = Linear_Float()
)

fn CR_bboxOf nodes =
(
	local mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9]
	for n in nodes where isValidNode n do
	(
		local bb = nodeGetBoundingBox n (matrix3 1)
		mn.x = amin mn.x bb[1].x; mn.y = amin mn.y bb[1].y; mn.z = amin mn.z bb[1].z
		mx.x = amax mx.x bb[2].x; mx.y = amax mx.y bb[2].y; mx.z = amax mx.z bb[2].z
	)
	#(mn, mx)
)

fn CR_isPart n = isValidNode n and (getUserProp n "CR_part") != undefined

fn CR_relink nodes newParent =
(
	for n in nodes where isValidNode n and n != newParent and not (CR_isPart n) do
		if n.parent == undefined or (findItem nodes n.parent) == 0 do n.parent = newParent
)

fn CR_makeDummy nm pos bsize col lay =
(
	local d = Dummy name:nm pos:pos boxsize:bsize wirecolor:col
	setUserProp d "CR_part" 1
	lay.addNode d
	d
)

fn CR_getNum n k def =
(
	local v = getUserProp n k
	if v == undefined then def
	else if classOf v == String then (local f = v as float; if f == undefined then def else f)
	else v
)

fn CR_smooth arr hw =
(
	hw = hw as integer
	local n = arr.count
	if hw < 1 then (for v in arr collect v)
	else
	(
		local out = #()
		for i = 1 to n do
		(
			local s = 0.0, c = 0
			for j = (amax 1 (i - hw)) to (amin n (i + hw)) do (s += arr[j]; c += 1)
			out[i] = s / c
		)
		out
	)
)

-- promedio solo hacia atras (causal): no mira frames futuros
fn CR_smoothPast arr hw =
(
	hw = hw as integer
	local n = arr.count
	if hw < 1 then (for v in arr collect v)
	else
	(
		local out = #()
		for i = 1 to n do
		(
			local s = 0.0, c = 0
			for j = (amax 1 (i - hw)) to i do (s += arr[j]; c += 1)
			out[i] = s / c
		)
		out
	)
)

-- tangente hiperbolica: saturacion suave hacia un tope
fn CR_tanh x =
(
	x = amax -20.0 (amin 20.0 x)
	local e = exp (2.0 * x)
	(e - 1.0) / (e + 1.0)
)

fn CR_readCA root t =
(
	local res = #(1.0, 0.0, 1.0, 0.0, 1.0)
	try
	(
		at time t
		(
			local ca = root.baseObject.CarRigControls
			res = #(ca.spinMult, ca.extraRPM, ca.steerMult, ca.steerOffset, ca.surfaceAmt)
		)
	)
	catch ()
	res
)

fn CR_shapeFilt o = (superClassOf o == Shape)

fn CR_progress p =
(
	try (CR_roSim.pb.value = p as integer) catch ()
	windows.processPostedMessages()
)

-- ============================================================================
--  Superficies procedurales (entrada x,y en cm de mundo, salida altura en cm)
-- ============================================================================
fn CR_hash ix iy sd =
(
	local s = (sin (ix * 127.1 + iy * 311.7 + sd * 74.7)) * 43758.5453
	s - (floor s)
)

fn CR_fbm p oct =
(
	local s = 0.0, a = 0.5, f = 1.0
	for k = 1 to oct do (s += a * (noise3 (p * f)); f *= 2.03; a *= 0.5)
	s
)

fn CR_surface preset x y sd =
(
	local so = sd * 17.31
	case preset of
	(
		-- asfalto liso
		1: (0.06 * (CR_fbm [x/6.0, y/6.0, so] 3)) + (0.15 * (CR_fbm [x/90.0, y/90.0, so + 5.0] 2))
		-- asfalto gastado
		2: (0.18 * (CR_fbm [x/8.0, y/8.0, so] 3)) + (0.6 * (CR_fbm [x/140.0, y/140.0, so + 5.0] 3))
		-- empedrado / adoquines (aparejo trabado)
		3:
		(
			local stoneL = 20.0, stoneW = 12.0
			local row = floor (y / stoneW)
			local u = x / stoneL
			if (mod (abs row) 2.0) > 0.5 do u += 0.5
			local cx = floor u
			local fu = u - cx
			local fv = (y / stoneW) - row
			local d = (sin (fu * 180.0)) * (sin (fv * 180.0))
			local dome = if d > 0.0 then (d ^ 0.35) else 0.0
			local hgt = 0.55 + 0.45 * (CR_hash cx row sd)
			(1.6 * dome * hgt) + (0.25 * (CR_fbm [x/150.0, y/150.0, so] 2))
		)
		-- ripio
		4: (0.45 * (CR_fbm [x/2.5, y/2.5, so] 2)) + (0.9 * (CR_fbm [x/35.0, y/35.0, so + 3.0] 3)) + (0.6 * (CR_fbm [x/200.0, y/200.0, so + 7.0] 2))
		-- camino de tierra
		5: (2.5 * (CR_fbm [x/180.0, y/180.0, so] 3)) + (0.5 * (CR_fbm [x/20.0, y/20.0, so + 2.0] 2))
		-- off-road
		6: (7.0 * (CR_fbm [x/320.0, y/320.0, so] 3)) + (2.0 * (CR_fbm [x/45.0, y/45.0, so + 4.0] 3))
		-- adoquin de granito antiguo: piedras 22x12 cm gastadas y redondeadas,
		-- cada una hundida distinto y la calzada asentada en ondas
		7:
		(
			local stoneL = 22.0, stoneW = 12.0
			local row = floor (y / stoneW)
			local u = x / stoneL
			if (mod (abs row) 2.0) > 0.5 do u += 0.5
			local cx = floor u
			local fu = u - cx
			local fv = (y / stoneW) - row
			local d = (sin (fu * 180.0)) * (sin (fv * 180.0))
			local dome = if d > 0.0 then (d ^ 0.6) else 0.0
			local h1 = CR_hash cx row sd
			local h2 = CR_hash cx row (sd + 5.3)
			local stone = 1.8 * dome * (0.6 + 0.4 * h1)
			local sunk = (h2 - 0.5) * 1.4 * (amin 1.0 (dome * 4.0))
			stone + sunk + (1.5 * (CR_fbm [x/400.0, y/400.0, so] 2)) + (0.5 * (CR_fbm [x/60.0, y/60.0, so + 2.0] 2))
		)
		-- empedrado de piedra bola: cantos rodados irregulares de ~16 cm
		8:
		(
			local cs = 16.0
			local gx = floor (x / cs), gy = floor (y / cs)
			local best = 0.0
			for i = -1 to 1 do
				for j = -1 to 1 do
				(
					local ccx = gx + i, ccy = gy + j
					local px = (ccx + 0.15 + 0.7 * (CR_hash ccx ccy sd)) * cs
					local py = (ccy + 0.15 + 0.7 * (CR_hash ccx ccy (sd + 3.1))) * cs
					local r = cs * 0.62 * (0.8 + 0.4 * (CR_hash ccx ccy (sd + 7.7)))
					local dd = (sqrt ((x - px) ^ 2 + (y - py) ^ 2)) / r
					if dd < 1.0 do
					(
						local hgt = 3.0 * (sqrt (1.0 - dd * dd)) * (0.6 + 0.4 * (CR_hash ccx ccy (sd + 1.9)))
						if hgt > best do best = hgt
					)
				)
			best + (2.0 * (CR_fbm [x/300.0, y/300.0, so] 2))
		)
		default: 0.0
	)
)

fn CR_groundH grounds p upV rayH =
(
	local best = undefined
	local rr = ray (p + upV * rayH) (-upV)
	for g in grounds do
	(
		local hit = intersectRay g rr
		if hit != undefined do
		(
			local d = dot (hit.pos - p) upV
			if best == undefined or d > best do best = d
		)
	)
	best
)

-- ============================================================================
--  Crear rig de dummies
--  ROOT > W_POS (ubicacion) > W_SIM (bake: altura) > W_OFS (manual) > W_STEER (bake) > W_SPIN (bake)
--  ROOT > BODY_POS (ubicacion) > BODY_SIM (bake) > BODY_OFS (manual)
-- ============================================================================
fn CR_createRig nm fwd refNodes =
(
	local fwdV = CR_fwdVec fwd
	local latV = cross fwdV [0,0,1]      -- eje de cabeceo (+ = trompa arriba)
	local leftV = -latV                  -- izquierda del conductor
	local upm = CR_unitsPerMeter()
	local ctr = [0,0,0], gz = 0.0
	local wb = 2.7 * upm, track = 1.6 * upm, rad = 0.33 * upm

	if refNodes.count > 0 do
	(
		local bb = CR_bboxOf refNodes
		local ext = bb[2] - bb[1]
		local lenF = if (abs fwdV.y) > 0.5 then ext.y else ext.x
		local lenL = if (abs fwdV.y) > 0.5 then ext.x else ext.y
		ctr = (bb[1] + bb[2]) / 2.0
		gz = bb[1].z
		wb = lenF * 0.6
		track = lenL * 0.84
		rad = amax (ext.z * 0.23) (0.15 * upm)
	)

	local rootPos = [ctr.x, ctr.y, gz]
	local axle = [0, 0, rad]
	local centers = #(
		rootPos + fwdV * (wb / 2.0) + leftV * (track / 2.0) + axle,
		rootPos + fwdV * (wb / 2.0) - leftV * (track / 2.0) + axle,
		rootPos - fwdV * (wb / 2.0) + leftV * (track / 2.0) + axle,
		rootPos - fwdV * (wb / 2.0) - leftV * (track / 2.0) + axle
	)
	local spinIdx = (CR_axisInfo leftV)[1]
	local pitchIdx = (CR_axisInfo latV)[1]
	local rollIdx = (CR_axisInfo fwdV)[1]

	local lay = LayerManager.getLayerFromName (nm + "_RIG")
	if lay == undefined do lay = LayerManager.newLayerFromName (nm + "_RIG")

	-- ROOT
	local root = CR_makeDummy (nm + "_ROOT") rootPos (CR_boxSize fwdV (wb * 1.7) (track * 1.3) (rad * 0.08)) yellow lay
	custAttributes.add root CR_CADef

	local tx = Text text:"FRENTE" size:(track * 0.22) name:(nm + "_FRENTE") wirecolor:yellow
	tx.pos = rootPos + fwdV * (wb * 0.95)
	tx.parent = root
	setUserProp tx "CR_part" 1
	lay.addNode tx

	-- CARROCERIA
	local bPos = [ctr.x, ctr.y, gz + rad]
	local bP = CR_makeDummy (nm + "_BODY_POS") bPos (CR_boxSize fwdV (wb * 1.25) (track * 0.95) (rad * 0.3)) orange lay
	local bSim = CR_makeDummy (nm + "_BODY_SIM") bPos (CR_boxSize fwdV (rad * 0.6) (rad * 0.6) (rad * 0.6)) (color 180 90 0) lay
	local bOfs = CR_makeDummy (nm + "_BODY_OFS") bPos (CR_boxSize fwdV (wb * 0.8) (track * 0.55) (rad * 0.15)) green lay
	bP.parent = root
	bSim.parent = bP
	bOfs.parent = bSim
	setTransformLockFlags bSim #{1,2,3}
	CR_linearize bSim 3 #(pitchIdx, rollIdx)

	-- RUEDAS
	for w = 1 to 4 do
	(
		local c = centers[w]
		local base = nm + "_W" + CR_labels[w]
		local p  = CR_makeDummy (base + "_POS")   c (CR_boxSize fwdV (rad * 2.3) (rad * 0.9) (rad * 2.3)) orange lay
		local s  = CR_makeDummy (base + "_SIM")   c [rad * 0.35, rad * 0.35, rad * 0.35] (color 180 90 0) lay
		local o  = CR_makeDummy (base + "_OFS")   c [rad * 0.5, rad * 0.5, rad * 0.5] green lay
		local st = CR_makeDummy (base + "_STEER") c [rad * 0.65, rad * 0.65, rad * 0.65] blue lay
		local sp = CR_makeDummy (base + "_SPIN")  c (CR_boxSize fwdV (rad * 1.4) (rad * 0.3) (rad * 1.4)) white lay
		p.parent = root
		s.parent = p
		o.parent = s
		st.parent = o
		sp.parent = st
		setTransformLockFlags s #{1,2,3}
		setTransformLockFlags st #{1,2,3}
		setTransformLockFlags sp #{1,2,3}

		-- circulo de radio en el plano de la rueda (dobla, no gira)
		local cr = Circle radius:rad name:(base + "_RADIO") wirecolor:yellow
		cr.transform = matrix3 fwdV [0,0,1] latV c
		cr.parent = st
		setUserProp cr "CR_part" 1
		lay.addNode cr

		CR_linearize s 3 #()
		CR_linearize st 0 #(3)
		CR_linearize sp 0 #(spinIdx)
	)

	setUserProp root "CR_isRig" 2
	setUserProp root "CR_name" nm
	setUserProp root "CR_fwd" fwd
	setUserProp root "CR_placing" 0
	root
)

fn CR_loadRig root =
(
	if not (isValidNode root) then return undefined
	if (CR_getNum root "CR_isRig" 0) < 2 then return undefined
	local rd = CR_RigData()
	rd.root = root
	rd.name = (getUserProp root "CR_name") as string
	rd.fwd = (CR_getNum root "CR_fwd" 2) as integer
	rd.radii = #(); rd.rests = #(); rd.poss = #(); rd.sims = #(); rd.ofss = #()
	rd.steers = #(); rd.spins = #(); rd.circles = #()
	for w = 1 to 4 do
	(
		local base = rd.name + "_W" + CR_labels[w]
		rd.poss[w] = getNodeByName (base + "_POS")
		rd.sims[w] = getNodeByName (base + "_SIM")
		rd.ofss[w] = getNodeByName (base + "_OFS")
		rd.steers[w] = getNodeByName (base + "_STEER")
		rd.spins[w] = getNodeByName (base + "_SPIN")
		rd.circles[w] = getNodeByName (base + "_RADIO")
		rd.radii[w] = 10.0
		rd.rests[w] = [0,0,0]
	)
	rd.bodyPos = getNodeByName (rd.name + "_BODY_POS")
	rd.bodySim = getNodeByName (rd.name + "_BODY_SIM")
	rd.bodyOfs = getNodeByName (rd.name + "_BODY_OFS")
	rd.bodyRest = [0,0,0]

	local ok = (isValidNode rd.bodyPos) and (isValidNode rd.bodySim) and (isValidNode rd.bodyOfs)
	for w = 1 to 4 do
		for nd in #(rd.poss[w], rd.sims[w], rd.ofss[w], rd.steers[w], rd.spins[w]) do
			if not (isValidNode nd) do ok = false
	if ok then rd else (messageBox "Faltan dummies del rig (se renombraron o borraron?)." title:"CarRig"; undefined)
)

-- relee posiciones de los *_POS y radios; valida el layout
fn CR_prepareRest rd =
(
	for w = 1 to 4 do
	(
		local cr = rd.circles[w]
		if isValidNode cr do rd.radii[w] = cr.radius * (length cr.transform.row1)
		rd.rests[w] = CR_localPos rd.poss[w]
	)
	rd.bodyRest = CR_localPos rd.bodyPos

	local fwdL = CR_fwdVec rd.fwd
	local leftL = cross [0,0,1] fwdL
	local frontC = (rd.rests[1] + rd.rests[2]) / 2.0
	local rearC = (rd.rests[3] + rd.rests[4]) / 2.0
	if (dot (frontC - rearC) fwdL) <= 0.0 do
	(
		messageBox "Las ruedas FL/FR tienen que quedar del lado del texto FRENTE." title:"CarRig"
		return false
	)
	if (dot (rd.rests[1] - rd.rests[2]) leftL) <= 0.0 or (dot (rd.rests[3] - rd.rests[4]) leftL) <= 0.0 do
	(
		messageBox "Izquierda/derecha invertidas: L = izquierda del conductor mirando hacia el FRENTE." title:"CarRig"
		return false
	)
	rd.wb = dot (frontC - rearC) fwdL
	rd.track = ((abs (dot (rd.rests[1] - rd.rests[2]) leftL)) + (abs (dot (rd.rests[3] - rd.rests[4]) leftL))) / 2.0
	true
)

fn CR_attachPath rd sp constVel startF endF =
(
	local pc = Path_Constraint()
	rd.root.pos.controller = pc
	pc.appendTarget sp 100.0
	pc.follow = true
	pc.constantVel = constVel
	pc.allowUpsideDown = false
	pc.bank = false
	case rd.fwd of
	(
		1: (pc.axis = 1; pc.axisFlip = false)
		2: (pc.axis = 1; pc.axisFlip = true)
		3: (pc.axis = 0; pc.axisFlip = false)
		default: (pc.axis = 0; pc.axisFlip = true)
	)
	local pctrl = getPropertyController pc "percent"
	if pctrl != undefined do deleteKeys pctrl #allKeys
	with animate on
	(
		at time startF pc.percent = 0.0
		at time endF pc.percent = 100.0
	)
)

fn CR_clearKeys rd reset =
(
	local fwdL = CR_fwdVec rd.fwd
	local latV = cross fwdL [0,0,1]
	local sIdx = (CR_axisInfo (-latV))[1]
	local pIdx = (CR_axisInfo latV)[1]
	local rIdx = (CR_axisInfo fwdL)[1]
	for w = 1 to 4 do
	(
		deleteKeys rd.sims[w].pos.controller[3].controller #allKeys
		deleteKeys rd.steers[w].rotation.controller[3].controller #allKeys
		deleteKeys rd.spins[w].rotation.controller[sIdx].controller #allKeys
		if reset do
		(
			rd.sims[w].pos.controller.Z_Position = 0.0
			CR_setRot rd.steers[w] 3 0.0
			CR_setRot rd.spins[w] sIdx 0.0
		)
	)
	deleteKeys rd.bodySim.pos.controller[3].controller #allKeys
	deleteKeys rd.bodySim.rotation.controller[pIdx].controller #allKeys
	deleteKeys rd.bodySim.rotation.controller[rIdx].controller #allKeys
	if reset do
	(
		rd.bodySim.pos.controller.Z_Position = 0.0
		CR_setRot rd.bodySim pIdx 0.0
		CR_setRot rd.bodySim rIdx 0.0
	)
)

-- ============================================================================
--  Modo UBICAR: desvincula modelos y congela dummies internos
-- ============================================================================
fn CR_innerNodes rd =
(
	local arr = #(rd.bodySim, rd.bodyOfs)
	for w = 1 to 4 do join arr #(rd.sims[w], rd.ofss[w], rd.steers[w], rd.spins[w])
	arr
)

fn CR_isPlacing rd = (CR_getNum rd.root "CR_placing" 0) > 0

fn CR_enterPlace rd =
(
	if CR_isPlacing rd do return true
	CR_clearKeys rd true
	local hosts = #(rd.root, rd.bodyPos) + (CR_innerNodes rd)
	for w = 1 to 4 do append hosts rd.poss[w]
	local pairs = #()
	for h in hosts do
		for c in h.children where not (CR_isPart c) do append pairs #(c, h)
	local links = ""
	for pr in pairs do
	(
		links += pr[1].name + ">" + pr[2].name + "|"
		pr[1].parent = undefined
	)
	setUserProp rd.root "CR_links" (if links == "" then "-" else links)
	for nd in (CR_innerNodes rd) do nd.isFrozen = true
	setUserProp rd.root "CR_placing" 1
	true
)

fn CR_exitPlace rd =
(
	if not (CR_isPlacing rd) do return true
	-- ubicadores sin rotacion, para que los ejes queden alineados al ROOT
	for w = 1 to 4 do CR_zeroRot rd.poss[w]
	CR_zeroRot rd.bodyPos
	for nd in (CR_innerNodes rd) do nd.isFrozen = false
	local links = getUserProp rd.root "CR_links"
	if links != undefined do
	(
		for pr in (filterString (links as string) "|") do
		(
			local ab = filterString pr ">"
			if ab.count == 2 do
			(
				local child = getNodeByName ab[1]
				local host = getNodeByName ab[2]
				if (isValidNode child) and (isValidNode host) do child.parent = host
			)
		)
	)
	setUserProp rd.root "CR_links" "-"
	setUserProp rd.root "CR_placing" 0
	true
)

-- ============================================================================
--  Simulacion + bake
-- ============================================================================
fn CR_bake rd o grounds startF endF progFn =
(
	local n = (endF - startF + 1) as integer
	if n < 2 do (messageBox "Rango de frames invalido." title:"CarRig"; return undefined)

	local dt = 1.0 / frameRate
	local upm = CR_unitsPerMeter()
	local cmU = upm / 100.0
	local gU = 9.81 * upm
	local rayH = 50.0 * upm
	local fwdL = CR_fwdVec rd.fwd
	local latL = cross fwdL [0,0,1]
	local spinInfo = CR_axisInfo (-latL)
	local pitchInfo = CR_axisInfo latL
	local rollInfo = CR_axisInfo fwdL
	local spinSgn = spinInfo[2] * (if o.invSpin then -1.0 else 1.0)
	local steerSgn = if o.invSteer then -1.0 else 1.0
	local hw = o.smoothFr as integer
	local antic = o.anticip as integer

	-- 1. muestrear el ROOT
	local TMs = #(), Ps = #(), Fs = #(), Us = #(), CAs = #()
	for i = 1 to n do
	(
		local t = startF + i - 1
		local tm = at time t rd.root.transform
		append TMs tm
		append Ps tm.row4
		append Fs (normalize (fwdL.x * tm.row1 + fwdL.y * tm.row2 + fwdL.z * tm.row3))
		append Us (normalize tm.row3)
		append CAs (CR_readCA rd.root t)
	)
	if progFn != undefined do progFn 10

	-- 2a. velocidad y yaw CENTRADOS: solo para la direccion (el conductor anticipa)
	local vs = #(), yaws = #()
	for i = 1 to n do
	(
		local ia = amax 1 (i - 1)
		local ib = amin n (i + 1)
		local span = (ib - ia) as float
		vs[i] = (dot (Ps[ib] - Ps[ia]) Fs[i]) / (span * dt)
		local sy = dot (cross Fs[ia] Fs[ib]) Us[i]
		local cy = dot Fs[ia] Fs[ib]
		yaws[i] = (atan2 sy cy) / (span * dt)      -- grados/seg
	)
	local vS = CR_smooth vs hw
	local yS = CR_smooth yaws hw

	-- 2b. velocidad, yaw y aceleracion CAUSALES: para la inercia de la carroceria.
	--     Solo usan frames pasados: el auto no reacciona antes de moverse.
	local vB = #(), yB = #()
	for i = 2 to n do
	(
		vB[i] = (dot (Ps[i] - Ps[i-1]) Fs[i]) / dt
		local sy = dot (cross Fs[i-1] Fs[i]) Us[i]
		local cy = dot Fs[i-1] Fs[i]
		yB[i] = (atan2 sy cy) / dt
	)
	vB[1] = vB[2]
	yB[1] = yB[2]
	local vC = CR_smoothPast vB hw
	local yC = CR_smoothPast yB hw
	local accB = #(0.0)
	for i = 2 to n do accB[i] = (vC[i] - vC[i-1]) / dt
	local accC = CR_smoothPast accB (hw / 2)

	-- 3. direccion (modelo bicicleta)
	local steerRaw = #(), prevSteer = 0.0, vmin = 0.15 * upm
	for i = 1 to n do
	(
		if o.autoSteer and (abs vS[i]) > vmin do
		(
			local yr = yS[i] * pi / 180.0
			prevSteer = atan (rd.wb * yr / vS[i])
			prevSteer = amax (-o.maxSteer) (amin o.maxSteer prevSteer)
		)
		steerRaw[i] = if o.autoSteer then prevSteer else 0.0
	)
	local steerA = for i = 1 to n collect steerRaw[amin n (i + antic)]
	if progFn != undefined do progFn 20

	-- 4. ruedas: piso + superficie + giro + direccion
	local offs = #(#(), #(), #(), #()), angs = #(#(), #(), #(), #()), stA = #(#(), #(), #(), #())
	local ang = #(0.0, 0.0, 0.0, 0.0)
	local prevC = #(undefined, undefined, undefined, undefined)
	local lastH = #(0.0, 0.0, 0.0, 0.0)
	for i = 1 to n do
	(
		local tm = TMs[i], fV = Fs[i], uV = Us[i], ca = CAs[i]
		local st = steerA[i] * ca[3] + ca[4]
		local sL = st, sR = st
		if o.ackermann and (abs st) > 0.05 do
		(
			local turnR = rd.wb / (tan (abs st))
			local inner = atan (rd.wb / (amax (turnR - rd.track / 2.0) (rd.wb * 0.05)))
			local outer = atan (rd.wb / (turnR + rd.track / 2.0))
			if st > 0 then (sL = inner; sR = outer) else (sR = -inner; sL = -outer)
		)
		for w = 1 to 4 do
		(
			local rad = rd.radii[w]
			local rest = rd.rests[w]
			local cW = rest * tm
			local contactW = (rest - [0, 0, rad]) * tm

			local gh = 0.0
			if grounds.count > 0 do
			(
				local hh = CR_groundH grounds contactW uV rayH
				if hh != undefined do lastH[w] = hh
				gh = lastH[w]
			)

			local bump = 0.0
			if ca[5] != 0.0 and o.amp != 0.0 do
			(
				local hp = rad * 0.22
				local samples = if o.envelope then #(-hp, -hp * 0.5, 0.0, hp * 0.5, hp) else #(0.0)
				local best = -1e9
				for so in samples do
				(
					local p = contactW + fV * so
					local hc = CR_surface o.preset (p.x / cmU / o.sizeMul) (p.y / cmU / o.sizeMul) o.seedV
					if hc > best do best = hc
				)
				bump = best * cmU * o.amp * ca[5]
			)
			offs[w][i] = gh + bump

			if prevC[w] != undefined do
			(
				local dW = dot (cW - prevC[w]) fV
				ang[w] += (dW / rad) * (180.0 / pi) * ca[1] + ca[2] * 6.0 * dt
			)
			prevC[w] = cW
			angs[w][i] = ang[w]
			stA[w][i] = case w of (1: sL; 2: sR; default: 0.0)
		)
		if progFn != undefined and (mod i 20) == 0 do progFn (20.0 + 40.0 * i / n)
	)

	-- 5. carroceria: resorte/amortiguador + inercia con tope + vibracion
	local bodyH = #(), bodyP = #(), bodyR = #()
	local w0 = 2.0 * pi * o.freq
	local zeta = o.damp
	local nSub = 10
	local hs = dt / nSub
	local xs = #(0.0, 0.0, 0.0), xv = #(0.0, 0.0, 0.0), lp = #(0.0, 0.0, 0.0)
	local alpha = dt / (0.06 + dt)
	local lims = #(1e9, (amax 0.01 o.maxPitch), (amax 0.01 o.maxRoll))
	for i = 1 to n do
	(
		local o1 = offs[1][i], o2 = offs[2][i], o3 = offs[3][i], o4 = offs[4][i]
		local frontA = (o1 + o2) / 2.0, rearA = (o3 + o4) / 2.0
		local leftA = (o1 + o3) / 2.0, rightA = (o2 + o4) / 2.0
		local latAcc = vC[i] * (yC[i] * pi / 180.0)
		-- pose geometrica (lo que marca el piso)
		local geo = #()
		geo[1] = (o1 + o2 + o3 + o4) / 4.0
		geo[2] = atan2 (frontA - rearA) rd.wb
		geo[3] = atan2 (leftA - rightA) rd.track
		-- inercia: crece con la aceleracion y se satura suave contra el tope
		local inP = (accC[i] / gU) * o.pitchG
		local inR = (latAcc / gU) * o.rollG
		inP = lims[2] * (CR_tanh (inP / lims[2]))
		inR = lims[3] * (CR_tanh (inR / lims[3]))
		local tgt = #(geo[1], geo[2] + inP, geo[3] + inR)
		if i == 1 then
		(
			for k = 1 to 3 do (xs[k] = tgt[k]; xv[k] = 0.0; lp[k] = tgt[k])
		)
		else
		(
			for k = 1 to 3 do
			(
				for ss = 1 to nSub do
				(
					local acc = w0 * w0 * (tgt[k] - xs[k]) - 2.0 * zeta * w0 * xv[k]
					xv[k] += acc * hs
					xs[k] += xv[k] * hs
					-- tope fisico: ni con el rebote pasa el maximo
					if k > 1 do
					(
						local dev = xs[k] - geo[k]
						if (abs dev) > lims[k] do
						(
							local sg = if dev > 0 then 1.0 else -1.0
							xs[k] = geo[k] + sg * lims[k]
							if (xv[k] * sg) > 0 do xv[k] = -xv[k] * 0.25
						)
					)
				)
				lp[k] += (tgt[k] - lp[k]) * alpha
			)
		)
		bodyH[i] = xs[1] + (tgt[1] - lp[1]) * o.vib
		bodyP[i] = xs[2] + (tgt[2] - lp[2]) * o.vib
		bodyR[i] = xs[3] + (tgt[3] - lp[3]) * o.vib
	)
	if progFn != undefined do progFn 65

	-- 6. escribir keys (offsets sobre los *_POS)
	CR_clearKeys rd false
	with animate on
	(
		for i = 1 to n do
		(
			local t = startF + i - 1
			at time t
			(
				for w = 1 to 4 do
				(
					rd.sims[w].pos.controller.Z_Position = offs[w][i]
					CR_setRot rd.steers[w] 3 (stA[w][i] * steerSgn)
					CR_setRot rd.spins[w] spinInfo[1] (angs[w][i] * spinSgn)
				)
				rd.bodySim.pos.controller.Z_Position = bodyH[i]
				CR_setRot rd.bodySim pitchInfo[1] (bodyP[i] * pitchInfo[2])
				CR_setRot rd.bodySim rollInfo[1] (bodyR[i] * rollInfo[2])
			)
			if progFn != undefined and (mod i 20) == 0 do progFn (65.0 + 35.0 * i / n)
		)
	)

	local vmax = 0.0
	for v in vS do if (abs v) > vmax do vmax = abs v
	#(vmax / upm * 3.6)
)

-- ============================================================================
--  Opciones <-> UI <-> ROOT
-- ============================================================================
fn CR_saveOpts root o =
(
	for k in CR_optKeys do setUserProp root ("CRopt_" + k) ((getProperty o (k as name)) as string)
	setUserProp root "CRopt_groundNames" (if o.groundNames == "" then "-" else o.groundNames)
)

fn CR_loadOpts root =
(
	local o = CR_Opts()
	for k in CR_optKeys do
	(
		local v = getUserProp root ("CRopt_" + k)
		if v != undefined do
		(
			if classOf v == String do v = try (execute v) catch undefined
			if v != undefined do setProperty o (k as name) v
		)
	)
	local g = getUserProp root "CRopt_groundNames"
	if g != undefined do o.groundNames = g as string
	o
)

-- presets de suspension: frecuencia, amortiguacion, vibracion, cabeceo/g, rolido/g, tope cabeceo, tope rolido
global CR_suspPresets = #(
	#(2.0, 0.50, 0.25, 1.5, 2.0, 1.8, 2.5),   -- Deportiva
	#(1.4, 0.35, 0.15, 2.5, 3.5, 3.0, 4.0),   -- Normal
	#(1.1, 0.28, 0.10, 3.5, 4.5, 4.0, 5.0),   -- Confort
	#(1.2, 0.30, 0.18, 3.5, 5.5, 4.5, 6.5),   -- SUV / camioneta
	#(1.05, 0.20, 0.30, 4.5, 6.0, 4.5, 6.5),  -- Auto 1940 (ballestas, amortiguadores de palanca)
	#(1.6, 0.22, 0.40, 3.0, 4.5, 3.5, 5.0)    -- Camion / utilitario 1940 (ballestas duras)
)

fn CR_gatherOpts =
(
	local o = CR_Opts()
	o.preset = CR_roDrive.ddPreset.selection
	o.amp = CR_roDrive.spAmp.value
	o.charSel = CR_roDrive.ddChar.selection
	o.freq = CR_roAdv.spFreq.value
	o.damp = CR_roAdv.spDamp.value
	o.vib = CR_roAdv.spVib.value
	o.pitchG = CR_roAdv.spPitchG.value
	o.rollG = CR_roAdv.spRollG.value
	o.maxPitch = CR_roAdv.spMaxP.value
	o.maxRoll = CR_roAdv.spMaxR.value
	o.sizeMul = CR_roAdv.spScale.value
	o.seedV = CR_roAdv.spSeed.value
	o.envelope = CR_roAdv.cbEnv.checked
	o.autoSteer = CR_roAdv.cbAuto.checked
	o.ackermann = CR_roAdv.cbAck.checked
	o.maxSteer = CR_roAdv.spMax.value
	o.smoothFr = CR_roAdv.spSmooth.value
	o.anticip = CR_roAdv.spAnt.value
	o.invSpin = CR_roAdv.cbInvSpin.checked
	o.invSteer = CR_roAdv.cbInvSteer.checked
	local gn = ""
	for g in CR_grounds where isValidNode g do gn += g.name + "|"
	o.groundNames = if gn == "" then "-" else gn
	o
)

fn CR_applyOpts o =
(
	CR_roDrive.ddPreset.selection = o.preset
	CR_roDrive.spAmp.value = o.amp
	CR_roDrive.ddChar.selection = o.charSel
	CR_roAdv.spFreq.value = o.freq
	CR_roAdv.spDamp.value = o.damp
	CR_roAdv.spVib.value = o.vib
	CR_roAdv.spPitchG.value = o.pitchG
	CR_roAdv.spRollG.value = o.rollG
	CR_roAdv.spMaxP.value = o.maxPitch
	CR_roAdv.spMaxR.value = o.maxRoll
	CR_roAdv.spScale.value = o.sizeMul
	CR_roAdv.spSeed.value = o.seedV
	CR_roAdv.cbEnv.checked = o.envelope
	CR_roAdv.cbAuto.checked = o.autoSteer
	CR_roAdv.cbAck.checked = o.ackermann
	CR_roAdv.spMax.value = o.maxSteer
	CR_roAdv.spSmooth.value = o.smoothFr
	CR_roAdv.spAnt.value = o.anticip
	CR_roAdv.cbInvSpin.checked = o.invSpin
	CR_roAdv.cbInvSteer.checked = o.invSteer
	CR_grounds = #()
	for nm in (filterString o.groundNames "|") do
	(
		local g = getNodeByName nm
		if isValidNode g do append CR_grounds g
	)
	CR_roDrive.updG()
)

fn CR_applySusp i =
(
	if i >= 1 and i <= CR_suspPresets.count do
	(
		local p = CR_suspPresets[i]
		CR_roAdv.spFreq.value = p[1]
		CR_roAdv.spDamp.value = p[2]
		CR_roAdv.spVib.value = p[3]
		CR_roAdv.spPitchG.value = p[4]
		CR_roAdv.spRollG.value = p[5]
		CR_roAdv.spMaxP.value = p[6]
		CR_roAdv.spMaxR.value = p[7]
	)
)

-- si no hay rig activo, intenta tomar el ROOT seleccionado
fn CR_tryAutoLoad =
(
	if (CR_currentRig == undefined or not (isValidNode CR_currentRig.root)) and selection.count == 1 do
	(
		local rd = CR_loadRig selection[1]
		if rd != undefined do
		(
			CR_roRig.setRig rd
			CR_applyOpts (CR_loadOpts rd.root)
		)
	)
	CR_currentRig != undefined and (isValidNode CR_currentRig.root)
)

fn CR_hasRig =
(
	if CR_tryAutoLoad() then true
	else
	(
		messageBox "Crea un rig, o selecciona el ROOT de uno existente." title:"CarRig"
		false
	)
)

-- ============================================================================
--  UI
-- ============================================================================
rollout CR_roRig "1 - RIG"
(
	edittext etName "Nombre:" text:"Car01" fieldWidth:160 align:#left
	dropdownlist ddFwd "Frente del auto apunta a:" items:#("+Y", "-Y", "+X", "-X") selection:2 width:222
	button btCreate "CREAR RIG" width:222 height:32 \
		tooltip:"Crea el rig de dummies. Si el auto esta seleccionado, los dummies se crean a su tamano. Sin seleccion (o con solo dummies seleccionados) usa medidas estandar."
	checkbutton ckPlace "UBICAR DUMMIES" width:222 height:28 highlightColor:(color 230 140 30) \
		tooltip:"Desvincula tus modelos y deja mover solo el ROOT, los *_POS naranjas y los circulos de radio (Radius = radio de la cubierta). Al apagarlo, o al simular, se re-linkea todo."
	button btSelPos "Seleccionar ubicadores" width:222 \
		tooltip:"Selecciona ROOT, BODY_POS, los 4 W??_POS y los circulos de radio."

	group "Linkear seleccion a"
	(
		button btFL "FL" width:49 across:4 tooltip:"Rueda delantera izquierda -> WFL_SPIN"
		button btFR "FR" width:49 tooltip:"Rueda delantera derecha -> WFR_SPIN"
		button btRL "RL" width:49 tooltip:"Rueda trasera izquierda -> WRL_SPIN"
		button btRR "RR" width:49 tooltip:"Rueda trasera derecha -> WRR_SPIN"
		button btLBody "Carroceria" width:102 across:2 tooltip:"Carroceria y todo lo que va con ella -> BODY_OFS"
		button btLCal "Calipers" width:102 tooltip:"Cada caliper -> STEER de la rueda mas cercana (doblan, no giran)"
	)

	button btLoad "Cargar rig seleccionado" width:222 tooltip:"Selecciona el ROOT de un rig existente y apreta aca."
	label lbRig "Sin rig activo" width:222

	fn syncPlace =
	(
		ckPlace.checked = (CR_currentRig != undefined) and (isValidNode CR_currentRig.root) and (CR_isPlacing CR_currentRig)
	)

	fn setRig rd =
	(
		CR_currentRig = rd
		lbRig.text = if rd == undefined then "Sin rig activo" else ("Rig activo:  " + rd.name)
		syncPlace()
	)

	fn needRigSel =
	(
		if selection.count == 0 then (messageBox "Selecciona las piezas a linkear." title:"CarRig"; false)
		else if CR_currentRig == undefined or not (isValidNode CR_currentRig.root) then
		(
			messageBox "Primero crea o carga un rig." title:"CarRig"
			false
		)
		else
		(
			-- linkear siempre fuera del modo ubicar y en reposo
			if CR_isPlacing CR_currentRig do CR_exitPlace CR_currentRig
			CR_clearKeys CR_currentRig true
			syncPlace()
			true
		)
	)

	fn linkWheel w =
	(
		if needRigSel() do
			undo "CarRig Link" on (CR_relink (selection as array) CR_currentRig.spins[w])
	)

	on CR_roRig open do CR_tryAutoLoad()

	on btCreate pressed do
	(
		local nm = substituteString etName.text " " "_"
		if (getNodeByName (nm + "_ROOT")) != undefined then
			messageBox ("Ya existe un rig llamado " + nm + ". Cambia el nombre.") title:"CarRig"
		else
		(
			-- medir solo el modelo: ignorar dummies de rigs existentes
			local refs = for s in selection where not (CR_isPart s) collect s
			local root
			undo "CarRig Create" on (root = CR_createRig nm ddFwd.selection refs)
			if root != undefined do
			(
				setRig (CR_loadRig root)
				select root
			)
		)
	)

	on ckPlace changed state do
	(
		if not (CR_hasRig()) then ckPlace.checked = false
		else
		(
			undo off
			(
				if state then CR_enterPlace CR_currentRig else CR_exitPlace CR_currentRig
			)
			if state do
			(
				CR_roSim.lbInfo.text = "Simulacion borrada: ubica los dummies"
				select (#(CR_currentRig.root, CR_currentRig.bodyPos) + CR_currentRig.poss)
			)
			redrawViews()
		)
	)

	on btSelPos pressed do
	(
		if CR_hasRig() do
		(
			local arr = #(CR_currentRig.root, CR_currentRig.bodyPos) + CR_currentRig.poss
			for c in CR_currentRig.circles where isValidNode c do append arr c
			select arr
		)
	)

	on btFL pressed do linkWheel 1
	on btFR pressed do linkWheel 2
	on btRL pressed do linkWheel 3
	on btRR pressed do linkWheel 4

	on btLBody pressed do
	(
		if needRigSel() do
			undo "CarRig Link" on (CR_relink (selection as array) CR_currentRig.bodyOfs)
	)

	on btLCal pressed do
	(
		if needRigSel() do
		(
			local sel = selection as array
			undo "CarRig Link" on
			(
				for b in sel where not (CR_isPart b) and (b.parent == undefined or (findItem sel b.parent) == 0) do
				(
					local bb = CR_bboxOf #(b)
					local bc = (bb[1] + bb[2]) / 2.0
					local best = 1, bd = 1e12
					for w = 1 to 4 do
					(
						local d = distance bc CR_currentRig.spins[w].pos
						if d < bd do (bd = d; best = w)
					)
					b.parent = CR_currentRig.steers[best]
				)
			)
		)
	)

	on btLoad pressed do
	(
		if selection.count != 1 then messageBox "Selecciona solo el ROOT del rig." title:"CarRig"
		else
		(
			local rd = CR_loadRig selection[1]
			if rd == undefined then messageBox "Eso no es un ROOT de CarRig (v1.2 o posterior)." title:"CarRig"
			else
			(
				setRig rd
				CR_applyOpts (CR_loadOpts rd.root)
			)
		)
	)
)

rollout CR_roDrive "2 - MANEJO"
(
	group "Recorrido (opcional)"
	(
		pickbutton pbPath "Elegir spline..." width:208 filter:CR_shapeFilt \
			tooltip:"Spline por donde va el auto. Tambien podes animar el ROOT a mano."
		checkbox cbConst "Velocidad constante" across:2 align:#left offset:[0,3] \
			tooltip:"Sin tildar: arranca y frena suave (keys de Percent editables)."
		button btAttach "Asignar" width:70 align:#right \
			tooltip:"Asigna el ROOT a la spline, en el rango de frames de SIMULAR."
	)

	group "Camino"
	(
		dropdownlist ddPreset "Superficie:" width:208 selection:3 \
			items:#("Asfalto liso", "Asfalto gastado", "Empedrado / adoquines", "Ripio", "Camino de tierra", "Off-road", "Adoquin antiguo (gastado)", "Empedrado piedra bola")
		spinner spAmp "Intensidad:" range:[0,20,1] type:#float fieldwidth:50 align:#right \
			tooltip:"Multiplica la altura de la superficie. Animable desde el ROOT (Superficie)."
		button btGAdd "Piso  <-  seleccion" width:138 across:2 align:#left \
			tooltip:"Terreno, rampas, cordones: las ruedas los siguen."
		button btGClr "Quitar" width:66 align:#right
		label lbG "Piso: plano del ROOT" width:208 align:#left
	)

	group "Suspension"
	(
		dropdownlist ddChar "Caracter:" width:208 selection:2 \
			items:#("Deportiva", "Normal", "Confort", "SUV / camioneta", "Auto 1940 (ballestas)", "Camion / utilitario 1940", "Personalizada")
	)

	fn updG =
	(
		lbG.text = if CR_grounds.count == 0 then "Piso: plano del ROOT" \
			else ("Piso: " + (CR_grounds.count as string) + " objeto(s)")
	)

	on ddChar selected i do CR_applySusp i

	on pbPath picked obj do (CR_path = obj; pbPath.text = obj.name)

	on btAttach pressed do
	(
		if not (isValidNode CR_path) then messageBox "Primero elegi una spline." title:"CarRig"
		else if CR_hasRig() do
			undo "CarRig Path" on (CR_attachPath CR_currentRig CR_path cbConst.checked CR_roSim.spS.value CR_roSim.spE.value)
	)

	on btGAdd pressed do
	(
		for g in selection where superClassOf g == GeometryClass and not (CR_isPart g) do appendIfUnique CR_grounds g
		updG()
	)
	on btGClr pressed do (CR_grounds = #(); updG())
)

rollout CR_roSim "3 - SIMULAR"
(
	spinner spS "Desde:" type:#integer range:[-100000,100000,0] fieldwidth:45 across:2 align:#left
	spinner spE "Hasta:" type:#integer range:[-100000,100000,100] fieldwidth:45 align:#right
	button btBake "SIMULAR" width:222 height:40 \
		tooltip:"Relee la posicion de los dummies y calcula ruedas, direccion y carroceria."
	progressbar pb color:(color 230 140 30) height:8 width:222
	label lbInfo "" width:222
	button btClear "Borrar simulacion" width:222

	on CR_roSim open do
	(
		spS.value = animationRange.start.frame as integer
		spE.value = animationRange.end.frame as integer
	)

	on btBake pressed do
	(
		if CR_hasRig() do
		(
			-- salir del modo ubicar (re-linkea modelos en reposo)
			if CR_isPlacing CR_currentRig do
			(
				undo off (CR_exitPlace CR_currentRig)
				CR_roRig.syncPlace()
			)
			if CR_prepareRest CR_currentRig do
			(
				local o = CR_gatherOpts()
				CR_saveOpts CR_currentRig.root o
				local grounds = for g in CR_grounds where isValidNode g collect g
				local t0 = timeStamp()
				local res
				lbInfo.text = "Simulando..."
				undo off (with redraw off (res = CR_bake CR_currentRig o grounds spS.value spE.value CR_progress))
				pb.value = 0
				if res != undefined do
					lbInfo.text = "Listo en " + (formattedPrint ((timeStamp() - t0) / 1000.0) format:".1f") + "s   |   Vel. max " + (formattedPrint res[1] format:".0f") + " km/h"
				redrawViews()
			)
		)
	)

	on btClear pressed do
	(
		if CR_hasRig() do
		(
			CR_clearKeys CR_currentRig true
			lbInfo.text = "Simulacion borrada"
			redrawViews()
		)
	)
)

rollout CR_roAdv "Ajustes avanzados"
(
	group "Suspension"
	(
		spinner spFreq "Frecuencia (Hz):" range:[0.3,6,1.4] type:#float fieldwidth:50 \
			tooltip:"Rigidez: mas alto = mas firme y rapida."
		spinner spDamp "Amortiguacion:" range:[0.05,2,0.35] type:#float fieldwidth:50 \
			tooltip:"Mas bajo = rebota mas antes de asentarse."
		spinner spVib "Vibracion:" range:[0,1,0.15] type:#float fieldwidth:50 \
			tooltip:"Cuanto del temblor del piso pasa directo a la carroceria."
		spinner spPitchG "Cabeceo (grados/g):" range:[0,20,2.5] type:#float fieldwidth:50 \
			tooltip:"Sensibilidad: cuanto se hunde la trompa al frenar / sube al acelerar, antes de llegar al tope."
		spinner spRollG "Rolido (grados/g):" range:[0,20,3.5] type:#float fieldwidth:50 \
			tooltip:"Cuanto se inclina en las curvas."
		spinner spMaxP "Tope cabeceo (grados):" range:[0.1,20,3.0] type:#float fieldwidth:50 \
			tooltip:"Maximo que se hunde o levanta la trompa por frenadas y arranques, por mas brusco que sea."
		spinner spMaxR "Tope rolido (grados):" range:[0.1,20,4.0] type:#float fieldwidth:50 \
			tooltip:"Maximo que se inclina en curvas."
	)
	group "Superficie"
	(
		spinner spScale "Tamano (x):" range:[0.05,20,1] type:#float fieldwidth:50 \
			tooltip:"1.0 = tamano real (adoquin 20-22 x 12 cm, piedra bola ~16 cm). 1.3 = piedras 30% mas grandes. No depende de las unidades de la escena."
		spinner spSeed "Seed:" range:[0,9999,1] type:#integer fieldwidth:50
		checkbox cbEnv "Envolvente del neumatico" checked:true \
			tooltip:"La cubierta puentea las juntas chicas en vez de meterse en cada hueco."
	)
	group "Direccion"
	(
		checkbox cbAuto "Automatica" checked:true across:2
		checkbox cbAck "Ackermann" checked:true
		spinner spMax "Giro max (grados):" range:[1,70,35] type:#float fieldwidth:50
		spinner spSmooth "Suavizado (frames):" range:[0,30,4] type:#integer fieldwidth:50 \
			tooltip:"Tambien define cuanto tarda la carroceria en reaccionar."
		spinner spAnt "Anticipacion (frames):" range:[0,30,2] type:#integer fieldwidth:50 \
			tooltip:"Cuantos frames antes de la curva empieza a doblar el volante."
	)
	group "Ejes"
	(
		checkbox cbInvSpin "Invertir giro" across:2 tooltip:"Si las ruedas giran al reves"
		checkbox cbInvSteer "Invertir direccion" tooltip:"Si doblan para el lado contrario"
	)

	fn markCustom = (try (CR_roDrive.ddChar.selection = CR_suspPresets.count + 1) catch ())
	on spFreq changed v do markCustom()
	on spDamp changed v do markCustom()
	on spVib changed v do markCustom()
	on spPitchG changed v do markCustom()
	on spRollG changed v do markCustom()
	on spMaxP changed v do markCustom()
	on spMaxR changed v do markCustom()
)

try (closeRolloutFloater CR_floater) catch ()
CR_floater = newRolloutFloater "CarRig v1.7" 262 780
addRollout CR_roRig CR_floater
addRollout CR_roDrive CR_floater
addRollout CR_roSim CR_floater
addRollout CR_roAdv CR_floater rolledUp:true
