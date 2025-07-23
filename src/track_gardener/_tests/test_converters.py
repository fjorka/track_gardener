from track_gardener.converters.nx_2_gardener import tracklet_roots_map

######################################################################
# test finding the root


def test_all_roots():
    # Every tracklet is its own root
    parent_map = {1: None, 2: None, 3: None}
    assert tracklet_roots_map(parent_map) == {1: 1, 2: 2, 3: 3}


def test_chain():
    # 1 <- 2 <- 3 <- 4
    parent_map = {1: None, 2: 1, 3: 2, 4: 3}
    assert tracklet_roots_map(parent_map) == {1: 1, 2: 1, 3: 1, 4: 1}


def test_multiple_chains():
    # Two separate chains: 1<-2<-3 and 10<-20
    parent_map = {1: None, 2: 1, 3: 2, 10: None, 20: 10}
    expected = {1: 1, 2: 1, 3: 1, 10: 10, 20: 10}
    assert tracklet_roots_map(parent_map) == expected


def test_orphan_and_chain():
    # 1<-2, 3 is orphan
    parent_map = {1: None, 2: 1, 3: None}
    expected = {1: 1, 2: 1, 3: 3}
    assert tracklet_roots_map(parent_map) == expected


def test_branching():
    # 1<-2, 1<-3, 1<-4 (star)
    parent_map = {1: None, 2: 1, 3: 1, 4: 1}
    expected = {1: 1, 2: 1, 3: 1, 4: 1}
    assert tracklet_roots_map(parent_map) == expected


def test_long_chain_with_shortcut():
    # 1<-2<-3<-4, but 3's root is already computed
    parent_map = {1: None, 2: 1, 3: 2, 4: 3}
    roots = tracklet_roots_map(parent_map)
    assert roots == {1: 1, 2: 1, 3: 1, 4: 1}
    # Test memorization (roots for 2, 3 already in roots dict when processing 4)


def test_large_forest():
    parent_map = {i: i - 1 if i % 5 != 0 else None for i in range(100)}
    expected = {i: i - (i % 5) for i in range(100)}
    assert tracklet_roots_map(parent_map) == expected


def test_root_points_to_none_but_missing_in_dict():
    # 99: None is not a key in parent_map, but root assignment should work
    parent_map = {1: None, 2: 1, 3: 99}
    # 1's root is itself, 2's root is 1, 3's root is 99
    expected = {1: 1, 2: 1, 3: 99}
    assert (
        tracklet_roots_map(parent_map) == expected
    ), f"Root mapping failed, expected: {expected}, got: {tracklet_roots_map(parent_map)}"


def test_self_parent_bug():
    # Should never happen, but make sure we don't infinite loop if parent==self
    parent_map = {1: 1, 2: 1}
    expected = {1: 1, 2: 1}
    assert tracklet_roots_map(parent_map) == expected
