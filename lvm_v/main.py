import json
import re
import subprocess
from jinja2 import Environment, FileSystemLoader, select_autoescape


def run_lvm_command(command):
    output = subprocess.run(
        [command, "--reportformat", "json"], stdout=subprocess.PIPE
    ).stdout

    data = json.loads(output)["report"][0][command[:-1]]

    return data


def run_lsblk():
    output = subprocess.run(["lsblk", "J"], stdout=subprocess.PIPE).stdout

    data = json.loads(output)["blockdevices"]

    return data


def find_mountpoint(lsblk, name):
    if len(lsblk) == 0:
        return None

    children = []
    for device in lsblk:
        if device["name"] == name:
            return device["mountpoint"]
        children.extend(device.get("children", []))

    return find_mountpoint(children, name)


def main():
    lvs = run_lvm_command("lvs")
    pvs = run_lvm_command("pvs")
    vgs = run_lvm_command("vgs")
    lsblk = run_lsblk()

    thins, lvs_no_thin = [], []
    for vol in lvs:
        if vol["lv_attr"][0] == "t":
            thins.append(vol)
        else:
            lvs_no_thin.append(vol)
            # Add fake thin pool for layout
            if not vol["pool_lv"]:
                thins.append({"fake": True})
    lvs = lvs_no_thin

    # Assign mount points to logical volumes from lsblk
    for vol in lvs:
        vol["mountpoint"] = find_mountpoint(lsblk, f'{vol["vg_name"]}-{vol["lv_name"]}')

    # Add disks and partitions from lsblk
    disks, partitions = [], []
    for disk in lsblk:
        name = f'/dev/{disk["name"]}'

        parts = 0
        for child in disk["children"]:
            if child["type"] == "part":
                part_name = f'/dev/{child["name"]}'
                partitions.append(
                    {
                        "name": part_name,
                        "size": child["size"].lower(),
                        "lvm_allocated": part_name in {pv["pv_name"] for pv in pvs},
                        "disk": name,
                        "fake": False,
                        "mountpoint": child["mountpoint"],
                    }
                )
                parts += 1

        lvm_allocated = name in {pv["pv_name"] for pv in pvs}
        disks.append(
            {
                "name": name,
                "size": disk["size"].lower(),
                "lvm_allocated": lvm_allocated,
                "parts": parts,
            }
        )
        # Add fake partitions for layout if lvm is using the whole disk
        if lvm_allocated:
            partitions.append(
                {
                    "name": f"{name}_fakepartition",
                    "size": "",
                    "lvm_allocated": False,
                    "disk": name,
                    "fake": True,
                }
            )

    env = Environment(
        loader=FileSystemLoader("lvm_v/templates"), autoescape=select_autoescape()
    )

    template = env.get_template("lvm.mermaid")

    rendered = template.render(
        lvs=lvs,
        pvs=pvs,
        vgs=vgs,
        disks=disks,
        partitions=partitions,
        thins=thins,
        render_mountpoints=True,
    )
    # FIXME: This doesn't work for some reason
    formatted = re.sub("\n{2,}", "\n\n", rendered)

    print(formatted)


if __name__ == "__main__":
    main()
