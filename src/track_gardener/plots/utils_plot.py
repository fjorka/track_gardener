"""
This module provides a functions to calculate the vertical positions of nodes.
"""

from typing import TYPE_CHECKING, Hashable

import networkx as nx
from walkerlayout import WalkerLayouting

if TYPE_CHECKING:
    from networkx import DiGraph


def set_y_with_walkerlayout(tree: "DiGraph", root_id: Hashable) -> "DiGraph":
    """Computes and sets the y-coordinate for tree nodes using the Walker algorithm.

    This function uses the Reingold-Tilford algorithm, as implemented in the
    `walkerlayout` library, to calculate the (x, y) positions of nodes in a
    tree. It then extracts the x-coordinate (vertical) and assigns it to a 'y'
    attribute for each node in the input graph.

    Args:
        tree: A NetworkX DiGraph representing the tree structure.
        root_id: The identifier of the root node from which the layout
            calculation should start.

    Returns:
        The input NetworkX DiGraph with the 'y' attribute set on each node.
    """

    # Create the layout
    layout = WalkerLayouting.layout_networkx(tree, root_id)

    # Set the "y" node attribute in the graph
    y_values = {node: x for node, (x, y) in layout.items()}
    nx.set_node_attributes(tree, y_values, "y")

    return tree
