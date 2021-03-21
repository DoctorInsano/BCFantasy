
-- 0: idle
-- 1: recording input
MODE = 0

-- 1: respond to ping
-- 2: send input state
-- 3: arbitrary write
-- 4: arbitrary read
LAST_COMMAND = nil

-- Preserve input mask across frames
INPUT_MASK = 0

--[[
resp_ = comm.socketServerResponse()
print(#resp_)
print(resp_)
string.byte(resp_, 0)
--]]

-- Main loop
while true do

    -- Check for user interaction
    buttons = input.get()
    -- byte 1 D-pad / select / start
    if buttons["J1 X+"] ~= nil then
        INPUT_MASK = bit.band(INPUT_MASK, 0x1)
    elseif buttons["J1 X-"] ~= nil then
        INPUT_MASK = bit.band(INPUT_MASK, 0x2)
    elseif buttons["J1 Y+"] ~= nil then
        INPUT_MASK = bit.band(INPUT_MASK, 0x4)
    elseif buttons["J1 Y-"] ~= nil then
        INPUT_MASK = bit.band(INPUT_MASK, 0x8)
    elseif buttons["J1 B7"] ~= nil then
        -- select
        INPUT_MASK = bit.band(INPUT_MASK, 0x10)
    elseif buttons["J1 B8"] ~= nil then
        -- start
        INPUT_MASK = bit.band(INPUT_MASK, 0x20)
    end

    -- skip next two bits

    -- byte 2 face buttons L / R
    if buttons["J1 B1"] ~= nil then
        -- A button
        INPUT_MASK = bit.band(INPUT_MASK, 0x100)
    elseif buttons["J1 B2"] ~= nil then
        -- B button
        INPUT_MASK = bit.band(INPUT_MASK, 0x200)
    elseif buttons["J1 B3"] ~= nil then
        -- X button
        INPUT_MASK = bit.band(INPUT_MASK, 0x400)
    elseif buttons["J1 B4"] ~= nil then
        -- Y button
        INPUT_MASK = bit.band(INPUT_MASK, 0x800)
    elseif buttons["J1 B5"] ~= nil then
        -- L button
        INPUT_MASK = bit.band(INPUT_MASK, 0x1000)
    elseif buttons["J1 B6"] ~= nil then
        -- R button
        INPUT_MASK = bit.band(INPUT_MASK, 0x2000)
    end

    -- Do we preserve the input mask?
    -- FIXME: by default this is the select button
    if buttons["J1 B7"] ~= nil then
        MODE = 1
    else
        MODE = 0
        if LAST_COMMAND ~= 2 then
            INPUT_MASK = 0
        end
    end

    -- check comms from the server
    resp = comm.socketServerResponse()

    if #resp == 0 then
        -- no op
    elseif string.byte(resp, 1) == 1 then
        -- ping
        LAST_COMMAND = 1
        comm.socketServerSend(string.char(1))
    elseif string.byte(resp, 1) == 2 then
        -- send input status
        LAST_COMMAND = 2
        --comm.socketServerSend(string.char(2))
        INPUT_MASK = 0xFF + 0x100 * 0xFF
        if MODE == 1 then
            -- indicate to server we're processing input
            comm.socketServerSend(string.char(2))
        elseif MODE == 0 and INPUT_MASK > 0 then
            -- blocked by https://github.com/TASVideos/BizHawk/issues/2194
            resp = string.char(2)
                    .. string.char(bit.band(INPUT_MASK, 0xFF))
                    .. string.char(bit.rshift(INPUT_MASK, 8))
            -- send result
            comm.socketServerSend(resp)
            -- avoid race conditions and repetition
            LAST_COMMAND = nil
        end
    elseif string.byte(resp, 1) == 3 then
        -- Write something to RAM
        -- where to write (unused right now, assumed to be WRAM)
        --write_to = string.byte(resp, 2)

        if #resp % 3 ~= 0 then
            -- Got an unexpected instruction size
            comm.socketServerSend(string.char(3) .. string.char(0))
        else
            for i=1,(#resp / 3) + 1,3 do
                b1, b2, b3 = string.byte(resp, i, 3)
                -- 2 byte location
                addr = b1 * 0x100 + b2
                -- 1 byte write value
                --print("Writing " .. b3 .. " to address " .. addr)
                --mainmemory.write_u8(addr, b3)
            end

            comm.socketServerSend(string.char(3))
        end
    elseif string.byte(resp, 1) == 4 then
        -- Write something to RAM
        -- where to read (unused right now, assumed to be WRAM, ROM is also an option)
        read_from = string.byte(resp, 2)

        -- exactly 8 bytes: 2 for command and location, 2 for start address
        -- and 4 for read length
        if #resp ~= 8 then
            -- Got an unexpected instruction size
            comm.socketServerSend(string.char(4) .. string.char(0))
        else
            -- 2 byte location
            b1, b2 = string.byte(resp, 3, 2)
            addr = b1 * 0x100 + b2
            -- 4 byte length
            b1, b2, b3, b4 = string.byte(resp, 5, 4)
            nbytes = (((b1 * 0x100 + b2) * 0x100 + b3) * 0x100 + b4)

            comm.socketServerSend(string.char(4))

            --[[
            resp = ""
            -- Work around for poor choices of indexing from the memory reading
            -- shift backwards by one and add one to the read
            -- then drop the zero index
            -- FIXME: boundary values
            addr = math.max(addr - 1, 0)
            nbytes = nbytes + 1
            for i,mem in pairs(mainmemory.readbytes(addr, nbytes)) do
                if i > 0 then
                    resp = resp .. mem
                end
                comm.socketServerSend(string.char(4) .. resp)
            end
            --]]
        end

    else
        print("Got unknown command " .. resp .. " " .. string.byte(resp, 1))
    end

    -- Write current events to screen
    gui.text(20, 240, "Mode: " .. MODE .. " Last Instruction: " .. LAST_COMMAND)
    local f = io.open("screen_choices.txt", "r")
    if f ~= nil then
        io.close(f)
        i = 0
        for line in io.lines("screen_choices.txt") do
            gui.text(20, 10 * (i + 1), line)
            i = i + 1
        end
    end


    emu.frameadvance()

end