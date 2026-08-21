from setuptools import setup

package_name = "swarmnet_master"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (
            f"share/{package_name}/launch",
            ["launch/swarm_grid.launch.py", "launch/mavros_fleet.launch.py"],
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    entry_points={"console_scripts": ["master_node = swarmnet_master.master_node:main"]},
)
