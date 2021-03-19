import os
from pathlib import Path
import numpy
from matplotlib import pyplot
from matplotlib.gridspec import GridSpec
import pandas
from . import read, _ACTOR_MAP

pth = Path(os.path.abspath(__file__)).parent.parent
_BOSS_INFO = pandas.read_csv(os.path.join(pth, "data/bc_fantasy_data_bosses.csv"))
IGNORE = {'', 'VICKS', 'WEDGE', 'BANON', 'LEO', 'EXTRA1', 'EXTRA2', 'EMPTY',
          'KUPEK', 'KUPOP', 'KURU', 'KUPAN', 'KURIN',
          'KUSHU', 'KUMAMA', 'KAMOG', 'KUTAN', 'KUKU'}

def report(fname):
    data = pandas.DataFrame(read.parse_log_file(fname))
    data.set_index("frame", inplace=True)

    fig = pyplot.figure(figsize=(15, 8))

    """
    all_party = set([read.translate([int(c) for c in n.split(' ') if c not in {'', '0'}])
                                            for n in itertools.chain(*[d.values() for d in data["party"].values])])
    """
    pdata = pandas.DataFrame([list(d) for d in data["cparty"]])
    pkills = pandas.DataFrame([d for d in data["kills"]])
    pdeaths = pandas.DataFrame([d for d in data["deaths"]])
    pdata.index = pkills.index = pdeaths.index = data.index
    # Ignore everything up to the first appearance of Terra
    idx = pdata[pdata == "TERRA"].index.min()
    #pdata = pdata[idx:]

    # Get party add order
    punique = pdata.T.unstack().unique()

    gs = GridSpec(1 + len(punique), 1)

    enc_ax = pyplot.subplot(gs[:1])
    enc_ax.set_xlim(data.index.min() / 60, data.index.max() / 60)
    enc_ax.set_ylim(0, 1)
    # FIXME: Make text box
    enc_ax.set_ylabel("Encounter Status", rotation=0)
    enc_ax.set_yticklabels([])
    enc_ax.spines['left'].set_visible(False)
    enc_ax.spines['right'].set_visible(False)
    enc_ax.spines['top'].set_visible(False)

    # In encounter
    enc_ax.fill_between(data.index / 60, 0, data["in_battle"].astype(int), color='red', step='pre', alpha=0.5)
    # In MIAB
    miab_enc = data["in_battle"] & data["is_miab"]
    enc_ax.fill_between(data.index / 60, 0, miab_enc.astype(int), color='blue', step='pre')
    # In boss encounter
    boss_enc = data["in_battle"] & data["eform_id"].isin(_BOSS_INFO["Id"])
    enc_ax.fill_between(data.index / 60, 0, boss_enc.astype(int), color='purple', step='pre')

    didx = numpy.logical_or.reduce(pdeaths.fillna(0).diff().astype(bool).values, axis=1)
    for death in pdeaths.index[didx]:
        enc_ax.axvline(death / 60, color='k')

    am = list(_ACTOR_MAP.values())
    for i, pmem in enumerate(sorted([p for p in punique if p not in IGNORE],
                                    key=lambda k: am.index(k.lower().capitalize()))):
    #for i, pmem in enumerate([p for p in punique]):
        in_party = (pdata == pmem).any(axis=1)

        pm_ax = pyplot.subplot(gs[1+i])
        pm_ax.spines['left'].set_visible(False)
        pm_ax.spines['right'].set_visible(False)
        pm_ax.spines['top'].set_visible(False)
        pm_ax.fill_between(in_party.index / 60, 0, (in_party.astype(int) & data.loc[in_party.index]["in_battle"]),
                           color=f"C{i}", step='pre', alpha=0.5)
        pm_ax.set_xlim(in_party.index.min() / 60, in_party.index.max() / 60)
        pm_ax.set_ylim(0, 1)
        # FIXME: Make text box
        pm_ax.set_ylabel(pmem, rotation=0)
        pm_ax.set_yticklabels([])

        if pmem not in pkills:
            continue

        kill_data = pkills[pmem].fillna(0).diff().astype(bool)
        for kill in kill_data[kill_data].index:
            pm_ax.axvline(kill / 60, color='k')

    pyplot.tight_layout()
    pyplot.savefig("timeline.png")

    return data