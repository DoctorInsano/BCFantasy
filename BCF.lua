kills = {}
-- in_battle requires the number of enemies and characters alive to be greater
-- than zero, and less than their allowed slot numbers (6 and 4 respectively).
-- It's probably not perfect, but seems to work so far
in_battle = memory.read_u8(0x3A76) > 0 and memory.read_u8(0x3A77) > 0
 	    and memory.read_u8(0x3A76) <= 4 and memory.read_u8(0x3A77) <= 6
enemies_alive = 0

-- character slot order
_CHARS = {
	"TERRA",
	"LOCKE",
	"CYAN",
	"SHADOW",
	"EDGAR",
	"SABIN",
	"CELES",
	"STRAGO",
	"RELM",
	"SETZER",
	"MOG",
	"GAU",
	"GOGO",
	"UMARO",
	"EXTRA1",
	"EXTRA2"
}

offset_lower = 169 - 112

-- At some point it would be nice to get this working
--ip = comm.socketServerGetIp()
--port = comm.socketServerGetPort()
ip = nil
port = nil

logfile = io.open("logfile.txt", "w+")

-- Main loop
while true do

	prev_state = in_battle
	in_battle = memory.read_u8(0x3A76) > 0 and --memory.read_u8(0x3A77) > 0 and
        	    memory.read_u8(0x3A76) <= 4 --and memory.read_u8(0x3A77) <= 6
	if prev_state ~= in_battle and in_battle then
		enemies_alive = memory.read_u8(0x3A77)
	end

	map_id = memory.read_u16_le(0x1F64)
	area_id = memory.read_u8(0x0520)
	miab_id = memory.read_u8(0x0789)

	-- need to learn offsets relative to ASCII
	--[[
	name_1 = string.char(math.max(memory.read_u8(0x2EAF) - offset_lower, 0))
	name_2 = string.char(math.max(memory.read_u8(0x2EB0) - offset_lower, 0))
	name_3 = string.char(math.max(memory.read_u8(0x2EB1) - offset_lower, 0))
	name_4 = string.char(math.max(memory.read_u8(0x2EB2) - offset_lower, 0))
	name_5 = string.char(math.max(memory.read_u8(0x2EB3) - offset_lower, 0))
	name_6 = string.char(math.max(memory.read_u8(0x2EB4) - offset_lower, 0))
	--]]

	atk_name_1 = string.char(math.max(memory.read_u8(0x57D5) - offset_lower, 0))
	atk_name_2 = string.char(math.max(memory.read_u8(0x57D6) - offset_lower, 0))
	atk_name_3 = string.char(math.max(memory.read_u8(0x57D7) - offset_lower, 0))
	atk_name_4 = string.char(math.max(memory.read_u8(0x57D8) - offset_lower, 0))
	atk_name_5 = string.char(math.max(memory.read_u8(0x57D9) - offset_lower, 0))
	atk_name_6 = string.char(math.max(memory.read_u8(0x57E0) - offset_lower, 0))

	-- next two work
	nchar_alive = memory.read_u8(0x3A76)
	nenem_alive = memory.read_u8(0x3A77)

	-- appears to work, but only for party, not enemies
	alive_mask = memory.read_u8(0x3A74)

	emu.frameadvance();

	gui.text(20, 10, "in battle? " .. tostring(in_battle) .. " | area id " .. area_id .. " | miab id " .. miab_id .. " | map id " .. map_id .. " | commmand name " .. atk_name_1 .. atk_name_2 .. atk_name_3 .. atk_name_4 .. atk_name_5 .. atk_name_6)
	gui.text(20, 20, "alive mask: " .. bizstring.binary((0xF + 1) + alive_mask) .. " total enemies " .. enemies_alive)
	gui.text(20, 30, "chars alive: " .. nchar_alive)
	gui.text(20, 40, "monsters alive: " .. nenem_alive)

	-- $EBFF-$EC06 monster names (4 items, 2 bytes each)
	-- must be pointers
	e1_name = string.char(math.max(memory.read_u8(0xEBFF) - offset_lower, 0)) .. 
		  string.char(math.max(memory.read_u8(0xEC00) - offset_lower, 0))

    	-- $EC07-$EC0E number of monsters alive for each name (4 items, 2 bytes each)
	e1_count = memory.read_u8(0xEC07)
	--gui.text(20, 70, "enemy slot 1: " .. e1_name .. " (" .. e1_count  .. ")")

	-- map slot to actor
	chars = {[0xFF] = "ERROR"}
	for i,char in ipairs(_CHARS) do
		cslot = memory.read_u8(0x3000 + i - 1)
		if cslot <= 0xF then
			-- Some weirdness here, so this is a manual fix
			--if cslot == 0 then
				--cslot = 1
			--end
			-- Why this is multiplied by two?
			chars[cslot] = char // 2
		elseif cslot ~= 0xFF then
			chars[cslot] = "ERROR slot reported -> " .. cslot
		end

		-- Strange mapping here
		if cslot == 0 then
			chars[1] = char
		elseif cslot == 2 then
			chars[2] = char
		elseif cslot == 4 then
			chars[4] = char
		elseif cslot == 6 then
			chars[8] = char
	end

	-- Crowd control potential
	--[[
	s = 5
	d = 6
	for j=0,3 do
		memory.write_u8(0x1602 + 0x25 * d + j, memory.read_u8(0x1602 + 0x25 * s + j))
	end
	j = 4
	-- increment character in certain position
	memory.write_u8(0x1602 + 0x25 * d + j, memory.read_u8(0x1602 + 0x25 * s + j) + 1)

	-- write char names to screen
	for i,char in ipairs(_CHARS) do
		cname = ""
		for j=0,5 do
			cname = cname .. string.char(math.max(memory.read_u8(0x1602 + 0x25 * (i - 1) + j) - offset_lower, 0))
		end
		
		gui.text(20, 360 + i * 10, i .. " " .. cname)
	end
	--]]

	-- targetting 0x3290 - 0x3297 slots 1-4 (indicates "masks")
	for i=0,3 do
		c_last_targetted = memory.read_u8(0x3290 + i)
		curr_hp = memory.read_u16_le(0x3BF4 + 2 * i)
		slot_mask = memory.read_u16_le(0x3018 + 2 * i)
		char_status_1 = memory.read_u16_le(0x2E98 + 2 * i)

		if slot_mask ~= 0xFF and chars[slot_mask] ~= nil then
			char = chars[slot_mask]
		else
			char = "EMPTY? (" .. slot_mask .. ")"
		end
		slot_mask = bizstring.hex(memory.read_u16_le(0x3018 + 2 * i))

		gui.text(20, 60 + i * 10, char .. " | slot " .. slot_mask .. " | " .. curr_hp .. " | targetted by: " .. bizstring.hex(c_last_targetted) .. " | status: " .. bizstring.binary(char_status_1))
	end

	-- 0x3298 monster slots 1-6? (indicates "masks")
	for i=0,5 do
		curr_hp = memory.read_u16_le(0x3BF4 + 8 + 2 * i)
		_slot_mask = memory.read_u16_le(0x3020 + 2 * i)
		slot_mask = bizstring.hex(memory.read_u16_le(0x3020 + 2 * i))
		status = ""

		-- Determine who killed this monster
		-- We must:
		-- 	* be in battle
		-- 	* not be an invalid (read nil) slot
		-- 	* not have an invalid (read nil) character targetting us
		-- 	* have curr_hp == 0 (this may not be sufficient)
		-- 	* have less enemies alive than last time we checked
		c_last_targetted = memory.read_u8(0x3298 + 2 * i)
		status = " killed by "
		if in_battle and _slot_mask ~= 255 and c_last_targetted ~= 255 and
		   curr_hp == 0 and nenem_alive < enemies_alive then
			status = status .. c_last_targetted

			-- Attribute kill to the last character that targetted this
			if c_last_targetted == 0 then
				c_last_targetted = 1
			end
			if c_last_targetted ~= nil then
				c_last_targetted = chars[c_last_targetted]
				-- How we get to this, I don't know...
				if c_last_targetted == nil then
					c_last_targetted = 'NIL lookup'
				end
			else
				-- Attempt to handle error
				c_last_targetted = "ERROR"
			end

			-- Initialize and/or increment
			if kills[c_last_targetted] == nil then
				kills[c_last_targetted] = 1
			else	
				kills[c_last_targetted] = kills[c_last_targetted] + 1
			end
			-- Decrement running enemy count
			enemies_alive = enemies_alive - 1
		--else
			--status = bizstring.hex(c_last_targetted)
		end

		gui.text(20, 120 + i * 10, "slot " .. slot_mask
					   .. " (" .. curr_hp .. ") targetted by: "
					   .. c_last_targetted
					   .. status)
	end

	-- Display kill tracker
	i = 0
	for char,kcount in pairs(kills) do
		gui.text(20, 240 + i * 10, "slot " .. char
					   .. " kills: " .. kcount)
		i = i + 1
    	end

	i = 0
	for char,slot in pairs(chars) do
		gui.text(20, 360 + i * 10, char .. " " .. slot)
		i = i + 1
	end

	frame_counter = emu.framecount()
	out_json = "{"
	-- General information
	out_json = out_json .. "\"frame\": " .. frame_counter .. ","
	out_json = out_json .. "\"miab_id\": " .. miab_id .. ","
	out_json = out_json .. "\"area_id\": " .. area_id .. ","
	out_json = out_json .. "\"map_id\": " .. map_id .. ","

	-- Kill information
	out_json = out_json .. "  \"kills\": {" .. ""
	i = 0
	for char,kcount in pairs(kills) do
		app =  ", "
		i = i + 1
		if i == #kills then
			app = ""
		end
		out_json = out_json .. "\"" .. char .. "\": " ..  kcount .. app
    	end
	out_json = out_json .. "}"

	out_json = out_json .. "}" 
	if in_battle then
		logfile:write(out_json .. "\n")
	end
end
