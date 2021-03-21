import random
from bcfcc import CCCommand, WriteArbitrary, SetStat

class Card(WriteArbitrary):
    def __init__(self, label, cost, tier=None):
        super().__init__(label, cost, None)
        self._tier = tier

    def sell(self, gm):
        gm.gp += self.cost

    def full(self, gm):
        pass

    def direct(self, gm):
        pass

class GainLevel(Card):
    """
    Full: 'Level up' a single (random char)
    Direct: +5 levels to all party (one battle)
    """
    def __init__(self):
        super().__init__("gain_level", 200, 1)

    def full(self, gm):
        # FIXME: this is only temporary
        return SetStat(self.label)(slot=random.randint(0, 3))

    def direct(self, gm):
        return SetStat(self.label)(slot=random.randint(0, 3))