import logging
import random
import functools

from bcf import read
from ff6_flags import NEGATIVE_STATUSES, ALL_STATUSES, UNUSABLE_STATUSES, STATUS_FLAGS, \
                      _validate_elems, ELEM_FLAGS

class CCCommand(object):
    def __init__(self, label, cost=None, requestor=None, admin_only=False):
        self.label = label
        self.cost = cost
        self._admin = admin_only
        self._req = requestor

    def precondition(self):
        return True

    def __call__(self, *args, **kwargs):
        return self.write(*args, **kwargs)

    def __del__(self):
        if self.cost is not None:
            pass

    def _add_to_queue(self, queue, *args, **kwargs):
        # FIXME: can do checks here?
        fcn = functools.partial(self, *args)
        t = queue.make_task(fcn, name=self.label, user=self._req, **kwargs)
        return t

    def write_seq(self, *args, **kwargs):
        to_write = []
        for addr, byt in zip(*args):
            to_write.extend([addr, byt])

        return self.write(*map(hex, to_write))

    def write(self, *args, **kwargs):
        """
        Write a sequence of one or more address / value pairs to memory.

        While this is used internally to send data to the emulator, it should be used (directly) only sparingly by admins as it can write arbitrary data to any location.
        """
        args = list(args)
        logging.info(f"write | input: {args}")
        # Need address value pairs
        assert len(args) % 2 == 0, f"write | arg len should be a multiple of 2, got {args}"

        instr = []
        while len(args) > 0:
            # assume hex
            addr = int(args.pop(0), 16)
            value = int(args.pop(0), 16) & 0xFF
            # Break into high byte, low byte, and value to write
            instr.extend(bytes([addr >> 8, addr & 0xFF, value]))

        logging.info(f"write | to write: {instr}")
        return instr

class WriteArbitrary(CCCommand):
    def __init__(self, requestor):
        super().__init__(label="write_arbitrary", cost=None, requestor=requestor, admin_only=True)

def write_arbitrary(*args, **kwargs):
    """
    Write a sequence of one or more address / value pairs to memory.

    While this is used internally to send data to the emulator, it should be used (directly) only sparingly by admins as it can write arbitrary data to any location.
    """
    args = list(args)
    logging.info(f"write_arbitrary | input: {args}")
    # Need address value pairs
    assert len(args) % 2 == 0, f"write_arbitrary | arg len should be a multiple of 2, got {args}"

    instr = []
    while len(args) > 0:
        # assume hex
        addr = int(args.pop(0), 16)
        value = int(args.pop(0), 16) & 0xFF
        # Break into high byte, low byte, and value to write
        instr.extend(bytes([addr >> 8, addr & 0xFF, value]))

    logging.info(f"write_arbitrary | to write: {instr}")
    return instr


def modify_item(*args):
    args = list(args)
    # FIXME: This will overwrite any item in this position\
    # FIXME: convert string to hex
    item = int(args.pop(0), 16)
    instr = [0x2686 >> 8, 0x2686 & 0xFF, item,
             0x2689 >> 8, 0x2689 & 0xFF, 0x1]
    # FIXME: increment

    return instr

class AddGP(CCCommand):
    _MAX_GP = 2 ** 24 - 1
    _BYTE_RANGE = list(range(0x1860, 0x1863))

    def __init__(self, requestor):
        super().__init__(label="add_gp", cost=None, requestor=requestor)

    def __call__(self, amnt=1000, *args, **kwargs):
        """
        !cc add_gp
        Add 1000 GP to total.

        Precondition: None
        """
        logging.info(f"add_gp | amount {amnt}, kwargs {[*kwargs.keys()]}")
        total_gp = sum([v << (8 * i) for i, v in enumerate(kwargs["field_ram"][0x1860:0x1863])])
        new_total = max(0, min(total_gp + amnt, self._MAX_GP))
        logging.info(f"add_gp | GP change {total_gp} -> {new_total}")

        to_write = []
        for addr, byt in zip(self._BYTE_RANGE, new_total.to_bytes(3, 'little')):
            to_write.extend([addr, byt])

        return self.write(*map(hex, to_write))


def add_gp(amnt=1000, **kwargs):
    """
    !cc add_gp
    Add 1000 GP to total.

    Precondition: None
    """
    logging.info(f"add_gp | amount {amnt}, kwargs {[*kwargs.keys()]}")
    total_gp = sum([v << (8 * i) for i, v in enumerate(kwargs["field_ram"][0x1860:0x1863])])
    new_total = max(0, min(total_gp + amnt, AddGP._MAX_GP))
    logging.info(f"add_gp | GP change {total_gp} -> {new_total}")

    to_write = []
    for addr, byt in zip(AddGP._BYTE_RANGE, new_total.to_bytes(3, 'little')):
        to_write.extend([addr, byt])

    return write_arbitrary(*map(hex, to_write))

class CantRun(CCCommand):
    _ADDR = 0x00B1
    # $11DF t-s---mc Field Equipment Effects
    #       t: tintinabar effect (doesn't work)
    #       s: sprint shoes effect (1.5x walk speed)
    #       m: moogle charm effect (no random battles)
    #       c: charm bangle effect (50% less random battles)
    _MASK = 1 << 2

    def __init__(self, requestor):
        super().__init__(label="cant_run", cost=None, requestor=requestor)
        self._toggle = True

    def _add_to_queue(self, queue):
        super()._add_to_queue(queue, state="battle")

    def __call__(self, *args, **kwargs):
        """
        !cc moogle_charm
        Prevent encounters for a certain amount of time (default 30 seconds)

        Precondition: None
        """
        logging.info(f"cant_run | toggle ({self._toggle}), kwargs {[*kwargs.keys()]}")

        # FIXME: do raw read here instead?
        val = kwargs["bf"]["cant_run"]
        logging.info(f"cant_run | toggle ({self._toggle}), pre toggle value {val}")
        if self._toggle is not None:
            val ^= self._MASK
        else:
            val |= self._MASK

        return self.write(hex(self._ADDR), hex(val))

def cant_run(toggle=None, **kwargs):
    mask = 1 << 2
    logging.info(f"cant_run | toggle ({toggle}), kwargs {[*kwargs.keys()]}")

    # FIXME: do raw read here instead?
    val = kwargs["bf"]["cant_run"]
    logging.info(f"cant_run | toggle ({toggle}), pre toggle value {val}")
    if toggle is not None:
        val ^= CantRun._MASK
    else:
        val |= CantRun._MASK

    return write_arbitrary(*[hex(CantRun._ADDR), hex(val)])

class MoogleCharm(CCCommand):
    _ADDR = 0x11DF
    # $11DF t-s---mc Field Equipment Effects
    #       t: tintinabar effect (doesn't work)
    #       s: sprint shoes effect (1.5x walk speed)
    #       m: moogle charm effect (no random battles)
    #       c: charm bangle effect (50% less random battles)
    _MASK = 1 << 1

    def __init__(self, requestor, duration=30):
        super().__init__(label="moogle_charm", cost=None, requestor=requestor)
        self.duration = duration

    def _add_to_queue(self, queue):
        # inelegant hack: find previous task by name in the queue and remove it
        t_off = [t for t in queue._q if t["name"] == self.label + "_off"]
        if len(t_off) > 0:
            t_off[0]["delay"] += self.duration
            return t_off[0]

        t_off = queue.make_task(self, name=self.label + "_off", user=self._req, enqueue=False)
        t = queue.make_task(self, name=self.label + "_on", user=self._req, duration=self.duration, callback=t_off)
        return t

    def __call__(self, *args, **kwargs):
        """
        !cc moogle_charm
        Prevent encounters for a certain amount of time (default 30 seconds)

        Precondition: None
        """
        logging.info(f"moogle_charm | kwargs {[*kwargs.keys()]}")

        # FIXME: do raw read here instead?
        val = kwargs["bf"]["field_relics"] ^ self._MASK
        logging.info(f"moogle_charm | post toggle value {val}")

        return self.write(hex(self._ADDR), hex(val))

def moogle_charm(toggle=True, **kwargs):
    # $11DF t-s---mc Field Equipment Effects
    #       t: tintinabar effect (doesn't work)
    #       s: sprint shoes effect (1.5x walk speed)
    #       m: moogle charm effect (no random battles)
    #       c: charm bangle effect (50% less random battles)
    mask = 1 << 1
    logging.info(f"moogle_charm | toggle ({toggle}), kwargs {[*kwargs.keys()]}")

    # FIXME: do raw read here instead?
    val = kwargs["bf"]["field_relics"]
    logging.info(f"moogle_charm | toggle ({toggle}), pre toggle value {val}")
    if toggle is not None:
        val ^= MoogleCharm._MASK
    else:
        val |= MoogleCharm._MASK

    return write_arbitrary(*[hex(MoogleCharm._ADDR), hex(val)])

class ActivateGolem(CCCommand):
    _BYTE_RANGE = [0x3A36, 0x3A37]
    # Other flags to set?
    # $3A81 - (used when $3A82 is loaded in 16-bit mode)
    # $3A82 Golem block targets (disabled if negative)
    # $AA Character 1 Block Type (-> $2C78) (0 = none, 1 = knife, 2 = sword, 3 = shield, 4 = zephyr cape, 5 = hand up, 6 = golem, 7 = dog)
    # $AB Character 2 Block Type (-> $2C79)
    # $AC Character 3 Block Type (-> $2C7A)
    # $AD Character 4 Block Type (-> $2C7B)

    def __init__(self, requestor):
        super().__init__(label="activate_golem", cost=None, requestor=requestor)

    def _add_to_queue(self, queue):
        super()._add_to_queue(queue, state="battle")

    def __call__(self, hp_val=None, *args, **kwargs):
        """
        !cc activate_golem
        Activates the "Earth Wall" effect for the duration of the battle. Default HP reservoir is 1000.

        Precondition: in battle
        """
        logging.info(f"activate_golem | hp_val {hp_val}")

        to_write = []
        for addr, byt in zip(self._BYTE_RANGE, int(hp_val).to_bytes(2, "little")):
            to_write.extend([addr, byt])

        return self.write(*map(hex, to_write))

def activate_golem(hp_val=1000, **kwargs):
    logging.info(f"activate_golem | hp_val {hp_val}")
    # Other flags to set?
    # $3A81 - (used when $3A82 is loaded in 16-bit mode)
    # $3A82 Golem block targets (disabled if negative)
    # $AA Character 1 Block Type (-> $2C78) (0 = none, 1 = knife, 2 = sword, 3 = shield, 4 = zephyr cape, 5 = hand up, 6 = golem, 7 = dog)
    # $AB Character 2 Block Type (-> $2C79)
    # $AC Character 3 Block Type (-> $2C7A)
    # $AD Character 4 Block Type (-> $2C7B)

    # FIXME: don't do this manually
    hp_val = int(hp_val)
    lowbyte, highbyte = hp_val & 0xFF, (hp_val >> 8)
    return write_arbitrary(*["0x3A36", hex(lowbyte), "0x3A37", hex(highbyte)])


def ole_cape(**kwargs):
    logging.info(f"ole_cape |")
    # by default, we do all?
    out, mask = [], 1 << 6
    for byt in range(0xAA, 0xAE):
        out.extend([byt, 1 << 6])

    return write_arbitrary(*map(hex, out))

class SetStatus(CCCommand):

    def __init__(self, requestor):
        super().__init__(label="random_status", cost=None, requestor=requestor, admin_only=True)

    def _add_to_queue(self, *args, queue):
        super()._add_to_queue(queue, *args, state="battle")

    def __call__(self, status, slot, **kwargs):
        """
        !cc set_status [slot #]
        [Admin Only] Apply any status to the specified slot

        Precondition: None
        """
        logging.info(f"set_status | status {status}, slot ({slot}), kwargs {[*kwargs.keys()]}")

        c = kwargs["party"][int(slot)]
        if status.startswith("-"):
            c.set_status(status[1:], clear=True)
        else:
            c.set_status(status)
        return self.write(*map(hex, c.flush()))

def set_status(status, slot=0, **kwargs):
    logging.info(f"set_status | status {status}, slot ({slot}), kwargs {[*kwargs.keys()]}")
    slot = int(slot)
    if slot < 0 or slot >= 4:
        raise IndexError(f"Invalid party slot {slot}.")

    c = kwargs["party"][slot]
    if status.startswith("-"):
        c.set_status(status[1:], clear=True)
    else:
        c.set_status(status)
    return write_arbitrary(*map(hex, c.flush()))

class Remedy(CCCommand):
    _REMEDY_CLEAR = NEGATIVE_STATUSES - {"wounded"}

    def __init__(self, requestor):
        super().__init__(label="remedy", cost=None, requestor=requestor)

    def precondition(self, slot, **kwargs):
        pmem = kwargs["party"][slot]
        is_dead = pmem.get_status_flags() & STATUS_FLAGS[0]["wounded"]
        #pmem.is_valid()
        #return pmem.is_valid() & not pmem.is_dead()
        return not is_dead

    def _add_to_queue(self, *args, queue):
        super()._add_to_queue(queue, *args, state="battle")

    def __call__(self, slot, *args, **kwargs):
        """
        !cc remedy [slot #]
        Remedy-like effect, remove all "negative" statuses (except wounded).

        Precondition: must be in battle, target must be valid and not dead
        """
        logging.info(f"remedy | args {args}, kwargs {[*kwargs.keys()]}")
        logging.info(f"remedy | clearing statuses for slot {slot}")

        c = kwargs["party"][slot]
        c.set_status(*list(self._REMEDY_CLEAR), clear=True)
        return self.write(*map(hex, c.flush()))

def remedy(*args, **kwargs):
    """
    !cc remedy [slot #]
    Remedy-like effect, remove all "negative" statuses (except wounded).

    Precondition: must be in battle, target must be valid and not dead
    """
    logging.info(f"remedy | args {args}, kwargs {[*kwargs.keys()]}")
    # FIXME: ensure slot is filled
    slot = args[0] if len(args) > 0 else random.randint(0, 3)
    logging.info(f"remedy | clearing statuses for slot {slot}")

    # FIXME: need to not affect other statuses
    if slot < 0 or slot >= 4:
        raise IndexError(f"Invalid party slot {slot}.")

    c = kwargs["party"][slot]
    c.set_status(*list(Remedy._REMEDY_CLEAR), clear=True)
    return write_arbitrary(*map(hex, c.flush()))

class RandomStatus(SetStatus):
    ALLOWED_STATUSES = list(ALL_STATUSES - UNUSABLE_STATUSES)

    def __init__(self, requestor):
        super().__init__(label="random_status", cost=None, requestor=requestor)

    def precondition(self, slot, **kwargs):
        pmem = kwargs["party"][slot]
        is_dead = pmem.get_status_flags() & STATUS_FLAGS[0]["wounded"]
        #pmem.is_valid()
        #return pmem.is_valid() & not pmem.is_dead()
        return not is_dead

    def _add_to_queue(self, *args, queue):
        super()._add_to_queue(queue, *args)

    def __call__(self, slot, *args, **kwargs):
        """
        !cc random_status [slot #]
        Apply a random status from a preselected list

        Precondition: must be in battle, target must be valid and not dead
        """
        logging.info(f"random_status | args {args}, kwargs {[*kwargs.keys()]}")
        status = random.choice(self.ALLOWED_STATUSES)
        logging.info(f"random_status | selected {status} status, inflicting on {slot}")
        return super()(status, slot=slot, **kwargs)

def random_status(*args, **kwargs):
    logging.info(f"random_status | args {args}, kwargs {[*kwargs.keys()]}")
    # FIXME: ensure slot is filled
    targ = args[0] if len(args) > 0 else random.randint(0, 3)
    status = random.choice(RandomStatus.ALLOWED_STATUSES)
    logging.info(f"random_status | selected {status} status, inflicting on {targ}")
    return set_status(status, slot=targ, **kwargs)

class Life1(CCCommand):
    def __init__(self, requestor):
        super().__init__(label="life_1", cost=None, requestor=requestor)

    def precondition(self, slot, **kwargs):
        pmem = kwargs["party"][slot]
        is_dead = pmem.get_status_flags() & STATUS_FLAGS[0]["wounded"]
        #return pmem.is_valid() & pmem.is_dead()
        return not is_dead

    def _add_to_queue(self, *args, queue):
        super()._add_to_queue(queue, *args, state="battle")

    def __call__(self, slot, *args, **kwargs):
        """
        !cc life_1 [slot #]
        Life-like effect, remove wounded status and restore some HP.

        Precondition: must be in battle, target must be valid and dead
        """
        logging.info(f"life_1 | args {args}, kwargs {[*kwargs.keys()]}")
        pmem = kwargs["party"][slot]
        # FIXME: move to Character class
        return set_status("-wounded", slot=slot, **kwargs) \
               + set_stat("cur_hp", val=pmem.max_hp / 16, slot=slot, **kwargs)

def life_1(*args, **kwargs):
    """
    !cc life_1 [slot #]
    Life-like effect, remove wounded status and restore some HP.

    Precondition: must be in battle, target must be valid and dead
    """
    logging.info(f"life_1 | args {args}, kwargs {[*kwargs.keys()]}")
    targ = args[0]
    pmem = kwargs["party"][targ]
    # FIXME: move to Character class
    return set_status("-wounded", slot=targ, **kwargs) \
           + set_stat("cur_hp", val=pmem.max_hp / 16, slot=targ, **kwargs)

class Life1(CCCommand):
    def __init__(self, requestor):
        super().__init__(label="life_1", cost=None, requestor=requestor)

    def precondition(self, slot, **kwargs):
        pmem = kwargs["party"][slot]
        is_dead = pmem.get_status_flags() & STATUS_FLAGS[0]["wounded"]
        #return pmem.is_valid() & pmem.is_dead()
        return not is_dead

    def _add_to_queue(self, *args, queue):
        super()._add_to_queue(queue, *args, state="battle")

    def __call__(self, slot, *args, **kwargs):
        """
        !cc life_2 [slot #]
        Life2-like effect, remove wounded status and restore all HP.

        Precondition: must be in battle, target must be valid and dead
        """
        logging.info(f"life_1 | args {args}, kwargs {[*kwargs.keys()]}")
        pmem = kwargs["party"][slot]
        # FIXME: move to Character class
        return set_status("-wounded", slot=slot, **kwargs) \
               + set_stat("cur_hp", val=pmem.max_hp, slot=slot, **kwargs)

def life_2(*args, **kwargs):
    """
    !cc life_2 [slot #]
    Life2-like effect, remove wounded status and restore all HP.

    Precondition: must be in battle, target must be valid and dead
    """
    logging.info(f"life_2 | args {args}, kwargs {[*kwargs.keys()]}")
    targ = args[0]
    pmem = kwargs["party"][targ]
    # FIXME: move to Character class
    return set_status("-wounded", slot=targ, **kwargs) \
           + set_stat("cur_hp", val=pmem.max_hp, slot=targ, **kwargs)

class Life3(SetStatus):
    def __init__(self, requestor):
        super().__init__(label="life3", cost=None, requestor=requestor)

    def precondition(self, slot, **kwargs):
        pmem = kwargs["party"][slot]
        #pmem.is_valid()
        #return pmem.is_valid()
        return True

    def _add_to_queue(self, *args, queue):
        super()._add_to_queue(queue, *args)

    def __call__(self, slot, *args, **kwargs):
        """
        !cc life_3 [slot #]
        Life3-like effect, adds life3 status to target.

        Precondition: must be in battle, target must be valid
        """
        logging.info(f"life3 | slot {slot}")
        return super()("life3", slot=slot, **kwargs)

def life_3(*args, **kwargs):
    """
    !cc life_3 [slot #]
    Life3-like effect, adds life3 status to target.

    Precondition: must be in battle, target must be valid
    """
    logging.info(f"life_3 | args {args}, kwargs {[*kwargs.keys()]}")
    targ = args[0] if len(args) > 0 else random.randint(0, 3)
    return set_status("life3", slot=targ, **kwargs)

class SetStat(CCCommand):
    def __init__(self, requestor):
        super().__init__(label="set_stat", cost=None, requestor=requestor, admin_only=True)

    def _add_to_queue(self, queue, *args):
        super()._add_to_queue(queue, *args, state="battle")

    def __call__(self, stat, val, slot, **kwargs):
        """
        !cc set_stat [stat] [value] [slot #]
        [Admin Only] Change the specified stat for the specified slot

        Precondition: None
        """
        logging.info(f"set_stat | stat / val ({stat} / {val}), kwargs {[*kwargs.keys()]}")
        slot = int(slot)
        if slot < 0 or slot >= 4:
            raise IndexError(f"Invalid party slot {slot}.")

        c = kwargs["party"][slot]
        c.change_stat(stat, int(val))
        return self.write(*map(hex, c.flush()))

def set_stat(stat, val, slot=0, **kwargs):
    logging.info(f"set_stat | stat / val ({stat} / {val}), kwargs {[*kwargs.keys()]}")
    slot = int(slot)
    if slot < 0 or slot >= 4:
        raise IndexError(f"Invalid party slot {slot}.")

    c = kwargs["party"][slot]
    c.change_stat(stat, int(val))
    return write_arbitrary(*map(hex, c.flush()))

class SetName(CCCommand):
    _BYTE_RANGE = list(range(0x1602, 0x1608))
    _CHAR_SIZE = 37

    def __init__(self, requestor):
        super().__init__(label="set_name", cost=None, requestor=requestor)

    def __call__(self, name, actor=0, **kwargs):
        """
        !cc set_name [name] [actor]

        Precondition: None
        """
        logging.info(f"set_name | name {name}, actor ({actor})")

        actor = int(actor)
        if actor < 0 or actor >= 16:
            raise IndexError(f"Invalid party index {actor}.")

        # FIXME: Automatically truncates
        _name = read.transcode(name)[:6]
        name = [255] * 6
        name[:len(_name)] = _name

        # FIXME: should do this on the Character side
        write = []
        off = actor * self._CHAR_SIZE
        for byt, chr in zip(self._BYTE_RANGE, name):
            write.extend([hex(byt + off), hex(chr)])

        return self.write(*write)

def set_name(name, actor=0, **kwargs):
    logging.info(f"set_name | name {name}, actor ({actor})")

    actor = int(actor)
    if actor < 0 or actor >= 16:
        raise IndexError(f"Invalid party index {actor}.")

    # FIXME: Automatically truncates
    _name = read.transcode(name)[:6]
    name = [255] * 6
    name[:len(_name)] = _name

    write = []
    off = actor * SetName._CHAR_SIZE
    for byt, chr in zip(SetName._BYTE_RANGE, name):
        write.extend([hex(byt + off), hex(chr)])
    return write_arbitrary(*write)

class NullifyElement(CCCommand):
    _ADDR = 0x3EC8

    def __init__(self, requestor):
        super().__init__(label="nullify_element", cost=None, requestor=requestor)
        self._toggle = True

    def _add_to_queue(self, queue):
        super()._add_to_queue(queue, state="battle")

    def __call__(self, elem, **kwargs):
        """
        !cc nullify_element [element]
        Toggle a ForceField like effect (nullification) of the specified element.

        Precondition: in battle
        """
        null_elems = kwargs["bf"]["null_elems"]
        logging.info(f"nullify_element | elem ({elem}), toggle: {self._toggle}, current value {hex(null_elems)}")
        if not _validate_elems(elem):
            raise ValueError(f"Invalid element {elem}")

        mask = ELEM_FLAGS[elem]
        if self._toggle is not None:
            null_elems ^= mask
        else:
            null_elems |= mask

        return self.write(*[hex(self._ADDR), hex(null_elems)])

def nullify_element(elem, toggle=True, **kwargs):
    null_elems = kwargs["bf"]["null_elems"]
    logging.info(f"nullify_element | elem ({elem}), toggle: {toggle}, current value {hex(null_elems)}")
    if not _validate_elems(elem):
        raise ValueError(f"Invalid element {elem}")

    mask = ELEM_FLAGS[elem]
    if toggle is not None:
        null_elems ^= mask
    else:
        null_elems |= mask

    return write_arbitrary(*[hex(NullifyElement._ADDR), hex(null_elems)])

class FallenOne(CCCommand):
    def __init__(self, requestor):
        super().__init__(label="fallen_one", cost=None, requestor=requestor)

    def precondition(self, slot, **kwargs):
        pmem = kwargs["party"][slot]
        is_dead = pmem.get_status_flags() & STATUS_FLAGS[0]["wounded"]
        #pmem.is_valid()
        #return pmem.is_valid() & not pmem.is_dead()
        return not is_dead

    def _add_to_queue(self, queue):
        super()._add_to_queue(queue, state="battle")

    def __call__(self, *args, **kwargs):
        """
        !cc fallen_one
        Immediately drop all party members HP to one.

        Precondition: must be in battle
        """
        logging.info(f"fallen_one | kwargs {[*kwargs.keys()]}")
        write = []
        for c in kwargs["party"]:
            # FIXME: check to make sure the character actually exists
            c.change_stat("cur_hp", 1)
            write.extend(list(map(hex, c.flush())))
        return self.write(*write)

def fallen_one(**kwargs):
    logging.info(f"fallen_one | kwargs {[*kwargs.keys()]}")
    write = []
    for c in kwargs["party"]:
        # FIXME: check to make sure the character actually exists
        c.change_stat("cur_hp", 1)
        write.extend(list(map(hex, c.flush())))
    return write_arbitrary(*write)

class TriggerBattle(CCCommand):
    _BYTE_RANGE = [0x1F6E, 0x1F6F]

    def __init__(self, requestor):
        super().__init__(label="pick_fight", cost=None, requestor=requestor)

    def _add_to_queue(self, queue):
        super()._add_to_queue(queue, state="field")

    def __call__(self, *args, **kwargs):
        # set 16-bit value at 0x1F6E to max --- this is faster than the extend strategy elsewhere
        to_write = ["0x1F6E", "0xFF", "0x1F6F", "0xFF"]
        return write_arbitrary(*to_write)

def trigger_battle(**kwargs):
    # set 16-bit value at 0x1F6E to max
    to_write = ["0x1F6E", "0xFF", "0x1F6F", "0xFF"]
    return write_arbitrary(*to_write)