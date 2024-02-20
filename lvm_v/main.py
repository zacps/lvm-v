import json
import subprocess
from jinja2 import Environment, FileSystemLoader, select_autoescape



def run_lvm_command(command):
    # output = subprocess.run([
    #     command,
    #     "--reportformat",
    #     "json"
    # ], stdout=subprocess.PIPE).stdout

    with open(f"lvm_v/{command}.json") as f:
        output = json.load(f)

    data = output["report"][0]

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
    lvs = run_lvm_command("lvs")["lv"]
    pvs = run_lvm_command("pvs")["pv"]
    vgs = run_lvm_command("vgs")["vg"]
    with open("lvm_v/lsblk.json") as f:
        lsblk = json.load(f)["blockdevices"]

    print(json.dumps(lvs, indent=2))
    print(json.dumps(pvs, indent=2))
    print(json.dumps(vgs, indent=2))
    print(json.dumps(lsblk, indent=2))

    # todo: identify and separate thinpools
    #thins = [vol for vol in lvs if vol["lv_attr"][0] == "t"]

    # Assign mount points to logical volumes from lsblk
    for vol in lvs:
        vol["mountpoint"] = find_mountpoint(lsblk, f'{vol["vg_name"]}-{vol["lv_name"]}')
        if vol["mountpoint"] is None:
            print("Failed to find mountpoint for ", f'{vol["vg_name"]}-{vol["lv_name"]}')

    # Add disks and partitions from lsblk
    disks, partitions = [], []
    for disk in lsblk:
        name = f'/dev/{disk["name"]}'

        parts = 0
        for child in disk["children"]:
            if child["type"] == "part":
                part_name = f'/dev/{child["name"]}'
                partitions.append({
                    "name": part_name,
                    "size": "",
                    "lvm_allocated": part_name in {pv["pv_name"] for pv in pvs},
                    "disk": name,
                    "fake": False
                })
                parts += 1

        lvm_allocated = name in {pv["pv_name"] for pv in pvs}
        disks.append({
            "name": name,
            "size": "",
            "lvm_allocated": lvm_allocated,
            "parts": parts
        })
        if lvm_allocated:
            partitions.append({
                "name": f"{name}_fakepartition",
                "size": "",
                "lvm_allocated": False,
                "disk": name,
                "fake": True
            })

    # Assign mount points to partitions (that aren't used in lvm) from lsblk

    env = Environment(
        loader=FileSystemLoader("lvm_v/templates"),
        autoescape=select_autoescape()
    )

    template = env.get_template("lvm.mermaid")

    print("---")

    print(template.render(lvs=lvs, pvs=pvs, vgs=vgs, disks=disks, partitions=partitions))

if __name__ == "__main__":
    main()