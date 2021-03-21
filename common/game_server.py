#import zmq
from PyEmuhawk import SocketServer
import random
import logging

class GameServer(SocketServer):
    def __init__(self, ip="127.0.0.1", port=54312):
        super().__init__(ip, port)

    def ping(self):
        self.connection.send(b"\x01")
        resp = self.connection.recv(1024)
        assert resp == b"\x01"
        logging.info("ping | server connection is established")
        return True

    def get_inputs(self, timeout=1, poll_inc=0.1):
        while timeout >= 0:
            self.connection.send(b"\x02")

            resp = self.connection.recv(1024)
            if not resp.startswith(b"\x02"):
                raise ValueError("Unexpected response to input poll.")
            if len(resp) > 1:
                resp = [*resp[1:]]
                break

            timeout -= poll_inc

        logging.info("get_inputs | client responded with inputs")
        return resp

    def write_to_emu(self, payload, memseg='ram'):
        self.connection.send(b"\x03\x00" + bytes(payload))

        resp = self.connection.recv(1024)
        if not resp.startswith(b"\x03"):
            raise ValueError("Unexpected response to write command.")
        if len(resp) > 1 and resp[1] == 0:
            raise ValueError("Write command encountered an error.")

    READ_REGIONS = {
        "ram": "\x00",
        "rom": "\x01"
    }
    def read_from_emu(self, addr, nbyt, memseg='ram', asdict=True):

        baddr = addr.to_bytes(2, "big")
        nbyt = addr.to_bytes(4, "big")
        self.connection.send(b"\x04" + self.READ_REGIONS[memseg] + baddr + nbyt)

        resp = self.connection.recv(1024)
        if not resp.startswith(b"\x04"):
            raise ValueError("Unexpected response to write command.")
        if len(resp) > 1 and resp[1] == 0:
            raise ValueError("Write command encountered an error.")

        if not asdict:
            return [*resp]
        return {addr + i: mem for i, mem in enumerate(resp)}

# https://stackoverflow.com/questions/36580931/python-property-factory-or-descriptor-class-for-wrapping-an-external-library
def _add_bound_property(self, prop_name, addr, nbytes=None, docstring=None):
    def getter(self):
        resp = self.read_from_emu(addr, nbytes or 1, asdict=False)
        resp = int.from_bytes(resp)
        self.__setattribute("_" + prop_name, resp)
        return resp

    def setter(self, value):
        #assert 0 <= v <= 0xFFFFFF
        self.write_seq(addr, value.to_bytes(nbytes, "big"))
        self.__setattr__("_" + prop_name, value)

    return property(getter, setter, doc=docstring)


_PROPERTIES = {
    "gp": {
        "addr": 0x1860,
        "nbytes": 3,
        "docstring": "Get and set GP"
    },
    "espers": {
        "addr": 0x1A69,
        "nbytes": 3,
        "docstring": "esper bit strings"
    },
    "party_commands": {
        "addr": 0x1616,
        "nbytes": 4,
        "docstring": "ids of party commands"
    },
    "known_swdtech": {
        "addr": 0x1CF7,
        "docstring": "known swdtech bit string"
    },
    "known_blitzes": {
        "addr": 0x1D28,
        "docstring": "known blitz bit string"
    },
    "known_rages": {
        "addr": 0x1D2C,
        "nbytes": 0x1D4B - 0x1D2C,
        "docstring": "known rages"
    },
    "known_dances": {
        "addr": 0x1D4C,
        "docstring": "known dance bit string"
    },
    "world_xy_position": {
        "addr": 0x1F60,
        "nbytes": 2,
        "docstring": "world map x / y position"
    },
    "airship_xy_position": {
        "addr": 0x1F62,
        "nbytes": 2,
        "docstring": "world map airship x / y position"
    },
    "party_xy_position": {
        "addr": 0x1FC0,
        "nbytes": 2,
        "docstring": "world map party x / y position"
    },
    "danger_counter": {
        "addr": 0x1F6E,
        "nbytes": 2,
        "docstring": "threat counter"
    }

}

def apply_properties(cls):
    for name, values in _PROPERTIES.items():
        setattr(cls, name, _add_bound_property(cls, name, **values))
    return cls

@apply_properties
class GameManager(GameServer):
    def __init__(self):
        super().__init__()
        self.ctx = None
        self._in_battle = None
        self._event_flags = None
        self.tiering = None

        # TODO: Get list of cards
        self.deck = self.shuffle_deck()

        self.hand = []

    def _checkpoint(self, fname=None):
        # use the property definitions?
        pass

    def in_battle(self):
        # FIXME: We may want to do additional logic checks or recheck some values
        # TODO:  we could also expand this to read the actor slots and
        # check patterns for state
        return self._in_battle

    def write_seq(self, start_addr, seq):
        to_write = []
        for i, b in zip([(start_addr + i).to_bytes(2, "big") for i in range(3)], seq):
            to_write.extend([*i] + [b])

        self.write_to_emu(start_addr, to_write)

    # async this
    def poll(self):
        # Eventually we'll want to switch all those memory reads to the engine
        from bcfcc.queue import CCQueue

        choice_processed = False
        while True:
            self.present_menu()

            if self.check_new_event() != 0:
                # we can look up the event, but it's not important right now
                # FIXME: Check for multiple event fires
                self.progress_tiering()

                self.hand.append(self.pick_card(None))

                # FIXME: implement checkpointing system
                # maybe do this? Check if newer?
                self.ctx = CCQueue().construct_game_context()
                choice_processed = False

            elif not choice_processed:
                # This will block on user input
                # Directly to file? New emulator command?
                resp = int.from_bytes(self.get_inputs(), "big")
                if resp:
                    # handle resp
                    self.map_resp_to_action(resp)
                    choice_processed = True

            # set this to whatever it needs to be to not overwhelm the emu
            sleep(1.0)

    def progress_tiering(self, ntiers=4):
        # less tier variance, use min
        # more tier variance
        # The length of this will influence the speed of upgrade
        self.tiering = self.tiering or [1, 1, 1, 1]
        self.tiering[random.randint(ntiers)] += 1

    def blank_char_slot(self, slot):
        pass

    def map_resp_to_action(self, resp):
        # FIXME: check that select was pushed?
        if resp & 0x800:
            # buy_draw
            pass
        elif resp & 0x100:
            for slot in range(4):
                if resp & (0x1 << slot):
                    # purch_char(slot)
                    break
        elif resp & 0x200:
            for slot in range(4):
                if resp & (0x1 << slot):
                    # use_card(slot)
                    break
                #use_card(-1)

    def check_new_event(self):
        from common import event_flags
        _old_flags = self._event_flags or 0
        nbytes = event_flags._EVENT_BIT_END - event_flags._EVENT_BIT_ADDR
        self._event_flags = self.read_from_emu(event_flags._EVENT_BIT_ADDR, nbytes)

        new_flags = _old_flags ^ self._event_flags

        return new_flags

    # this may become async
    def present_menu(self):
        menu = f"s + A + dir: purchase character\n" \
               f"s + Y: buy draw [{self.hand[-1].label}]\n" \
               f"s + B + dir: use card\n" \
               f"hand\n"
        for c in self.hand[:-1]:
            menu += f"\t[{c.label}]\n"
        # TODO: Write to status file

    def use_card(self, i):
        if i == -1:
            self.hand[-1].full()
        else:
            self.hand[i].direct()

    def pick_card(self, cards):
        tier = self.tiering[random.randint(len(self.tiering))]
        # FIXME: How deterministic is this going to be?
        # We can add some randomness too...
        self.deck = sorted(cards, key=lambda c: c.tier - tier)
        return self.deck[0]

if __name__ == "__main__":
    server = GameServer()
    server.create_connection()
    server.ping()