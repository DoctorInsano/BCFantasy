from bcf import read
# Most information from ff6_event_bits
_WOB_PROGRESSION_ORDER = {
    1 << 0: "Unused",
    1 << 1: "Met Arvis (disables a Magitek Armor-related function in the mines)",
    1 << 2: "Unused?",
    1 << 3: "Initiated the tripartite battle with the Moogles (pointless?)",
    1 << 4: "Named Edgar (affects Figaro Castle and Narshe)",
    1 << 5: "Named Sabin",
    1 << 6: "Met Kefka in Figaro Castle",


    1 << 7: "Saw Sabin say he has to wander around Figaro Castle for a while"
}

# event bits are stored in 96 bytes of RAM from address $1E80 to $1EDF in bank $7E.
_EVENT_BIT_ADDR = 0x1E80
_EVENT_BIT_END = 0x1EDF + 1
def get_event_bits(memfile="memfile"):
    mem = read.read_memory(memfile)
    assert _EVENT_BIT_ADDR in mem
    event_bits = mem[_EVENT_BIT_ADDR]
    assert len(event_bits) == _EVENT_BIT_END - _EVENT_BIT_ADDR

    return int.from_bytes(mem)