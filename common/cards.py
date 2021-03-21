from bcfcc import CCCommand, AddGP
from bcfcc import Character

class CheckpointRAM(CCCommand):
    def __init__(self, slot, memfile="memfile"):
        # I know, I know...
        super().__init__("checkpoint_ram", None, None)
        self._checkpoint = None

    def __call__(self, *args, **kwargs):
        # read memory in to checkpoint
        pass

    def _serialize(self, fname):
        pass

# Maybe from ContextAware too?
class BlankCharSlot(CCCommand, Character):
    def __init__(self, slot, memfile="memfile"):
        # I know, I know...
        CCCommand.__init__("blank_char_slot", None, None)
        Character.__init__()
        self._from_memory_range(memfile, slot)

    def __call__(self, *args, **kwargs):
        # Change stats, etc...
        pass

class Card(AddGP):
    def __init__(self, label, cost):
        super().__init__(label, cost, None)
        self._tier = None

    def sell(self):
        super().__call__(self.cost)

    def immediate(self):
        pass

