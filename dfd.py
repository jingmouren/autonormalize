from itertools import combinations
import numpy

from classes import BitIndexSet, LHSs, DfdDependencies, Node, Partitions


# see https://hpi.de/fileadmin/user_upload/fachgebiete/naumann/publications/2014/DFD_CIKM2014_p949_CRC.pdf for DFD paper
# run script.py  to see a couple examples

def dfd(df, accuracy):
    """
    Main loop of DFD algorithm. Refer to section 3.2 of papter for some literature.

    - checks each column to see if it's unique
        - if unique: it is the LHS of a dependency for every other element

    - loops through all other non-unique columns and determines all lhs that the
    column depends on
    """
    partitions = Partitions()
    masks = Masks(df.columns)
    attributes = df.columns
    length = len(attributes)
    unique_attrs = set()
    r = set(range(length))
    dependencies = DfdDependencies(attributes)
    for i in range(length):
        if df[attributes[i]].is_unique:
            unique_attrs.add(i)
            r.remove(i)
            for x in range(length):
                if x != i:
                    dependencies.add_LHS(x, BitIndexSet(length, set([i])))
    if len(r) > 1:
        for i in r:
            lhss = find_LHSs(i, r, df, unique_attrs, partitions, accuracy, masks)
            dependencies.add_LHSs(i, lhss)
    return dependencies


def find_LHSs(i, attrs, df, unique_attrs, partitions, accuracy, masks):
    """
    Looks for all LHS sets of attributes for the RHS attribute i.

    i: rhs on dependencies looking for

    attrs: all non-unique attributes

    df: dataframe for which determining dependencies from

    unique_attrs: all the unique attributes

    partitions: partitions object with past calculated partitions


    Process:
    - generates seeds for all of the attributes to look at and builds lattice graph
    - chooses a random node
        - if node is visited:
            - if it is a candidate, checks if it can be updated category
            * see node documentation for category descriptions
        - if node is not visited:
            - attempt to infer type
            - else... partition to determine type
    - for picking next node: if is dependency, move back in trace, if is non-dependency move up
    -  if out of seeds, check for new seeds based off of the fact that pruning may have lead
    to missing some elements on this run
    """
    lhs_attrs = attrs.difference(set([i]))
    seeds = nodes_from_seeds(len(df.columns), lhs_attrs)
    min_deps = LHSs(lhs_attrs, True)
    max_non_deps = LHSs(lhs_attrs, False)
    trace = []  # could make this into a linked list...  (and stack in Node class)
    while seeds != []:
        node = seeds[0]  # should this be actually random
        while node is not None:
            if node.visited:

                    if node.is_candidate():
                        if node.is_dependency():
                            if node.is_minimal():
                                min_deps.add_dep(node.attrs)
                        else:
                            if node.is_maximal():
                                max_non_deps.add_dep(node.attrs)
                        node.update_dependency_type(min_deps, max_non_deps)

            else:
                node.infer_type()
                if node.category == 0:
                    if compute_partitions(df, i, node.attrs, partitions, accuracy, masks):
                        if node.is_minimal():
                            min_deps.add_dep(node.attrs)
                            node.category = 2
                        else:
                            node.category = 3
                    else:
                        if node.is_maximal():
                            max_non_deps.add_dep(node.attrs)
                            node.category = -2
                        else:
                            node.category = -3
                node.visited = True

            node = pick_next_node(node, trace, min_deps, max_non_deps)

        seeds = nodes_from_seeds(len(df.columns), generate_next_seeds(max_non_deps, i, unique_attrs, min_deps))
    return min_deps


def nodes_from_seeds(size, seeds):
    """
    Creates nodes from seeds and returns them.

    - Cretes a node for each seed
    - Calls make_lattice which connects them and forms the rest of the lattice graph
    """
    base_nodes = []
    for attr in seeds:
        base_nodes.append(Node(BitIndexSet(size, set([attr]))))
    make_lattice(base_nodes, size)
    return base_nodes


def make_lattice(nodes, size):
    """
    Builds the rest of the lattice graph given a list of seed nodes.
    To do this it must create nodes for all possible subsets of the seeds,
    and connect each of them to their subsets, and their supersets so that
    a lattice is formed.
    """
    if len(nodes) < 2:
        return
    # TODO: Inefficient, but straight forward --> optimize
    this_level_size = len(nodes[0].attrs)
    attrs = set()
    for n in nodes:
        for x in n.attrs:
            attrs.add(x)
    next_level = []
    combos = combinations(attrs, this_level_size+1)
    for new_attrs in combos:
        new_attr_set = BitIndexSet(size, new_attrs)
        new_node = Node(new_attr_set)
        for n in nodes:
            if n.attrs.is_subset(new_attr_set):
                new_node.add_prev(n)
                n.add_next(new_node)
        next_level.append(new_node)
    make_lattice(next_level, size)
    # for i in range(len(nodes)-1):
    #     for j in range(i+1, len(nodes)):
    #         new_attrs = (nodes[i].attrs).union(nodes[j].attrs)
    #         prev = [nodes[i], nodes[j]]
    #         for n in nodes[j+1:]:
    #             if n.attrs.issubset(new_attrs):
    #                 prev.append(n)
    #         new_node = Node(new_attrs, prev, [])
    #         next_level.append(new_node)\


def sort_key(node):
    intt = 0
    attrs = sorted(list(node.attrs))
    for i in range(len(attrs)):
        intt += (10**attrs[i])
    return intt


def pick_next_node(node, trace, min_deps, max_non_deps):
    """
    If is candidate min dependency:
        - if no unchecked subsets that could be dependnecy: --> must be min-dependency
        - else: check that subset
    If is candidate max non-dependency:
        - if no unchecked supersets that could be non-dependency: --> must be max non-dependency
        - else: check that superset
    Else:
        - return last node on trace (go back down in graph)
    """
    if node.category == 3:
        s = node.unchecked_subsets()
        remove_pruned_subsets(s, min_deps)
        if s == []:
            min_deps.add_dep(node.attrs)
            node.category = 2
        else:
            trace.append(node)
            return s[0]  # should this be randomized?????

    elif node.category == -3:
        s = sorted(node.unchecked_supersets(), key=sort_key)
        remove_pruned_supersets(s, max_non_deps)
        if s == []:
            max_non_deps.add_dep(node.attrs)
            node.category = -2
        else:
            trace.append(node)
            return s[0]

    else:
        if trace == []:
            return None
        return trace.pop()


def remove_pruned_subsets(sets, min_deps):
    """
    - if is a subset of a min-dependency, must be dependent
    """
    for n in sets[:]:
        if min_deps.contains_superset(n.attrs):
            sets.remove(n)


def remove_pruned_supersets(supersets, max_non_deps):
    """
    - if is a superset of a max-non-dependency, must be non-dependent
    """
    for n in supersets[:]:
        if max_non_deps.contains_subset(n.attrs):
            supersets.remove(n)


def generate_next_seeds(max_non_deps, rhs, uniques_set, min_deps):
    """
    Generates seeds for nodes that are still unchecked due to agressive pruning.

    Method:
    when every possibility has been considered, the complement of max non-dependencies
    minus the existing min dependencies is 0 (they are equal).
    If this is not satisfied:
    New seeds are the remaining elements
    """
    seeds = set()
    if max_non_deps.all_sets() == set():
        seeds = (min_deps.all_sets().pop().get_compliment(rhs)).to_set()
        # seeds.difference(uniques_set)
    else:
        for nfd in max_non_deps.all_sets():
            nfd_compliment = nfd.get_compliment(rhs)
            # nfd_compliment.difference(uniques_set)
            if len(seeds) == 0:
                seeds = nfd_compliment.to_set()
            else:
                seeds = seeds.intersection(nfd_compliment.to_set())
    for x in min_deps.all_sets():
        seeds = seeds.difference(x)
    seeds = seeds.difference(uniques_set)
    return list(seeds)


def compute_partitions(df, rhs, lhs_set, partitions, accuracy, masks):
    """
    Determines whether lhs_set --> rhs for dataframe df.

    df: the dataframe storing data
    rhs: the rhs on dependency investigating
    lhs_set: set of attributes on lhs of dependency investigating
    partitions: partitions object storing past computed partitions

    Determines the number of equivilence classes for columns in lhs_set.
    Determines the number of equivilence classes for columns in lhs_set and rhs.

    If less than 10% of rows are repititions:
        - No dependency

    If number of equivilence classes is the same:
        - Dependency
    Else:
        - No dependency
    """
    # for approximate dependencies see TANE section 2.3
    return approximate_dependencies(lhs_set, rhs, df, accuracy, masks)





    partition_lhs = partition(lhs_set, df, partitions)
    partition_rhs = partition(lhs_set.add_new(set([rhs])), df, partitions)
    if partition_rhs > df.shape[0]*0.90:
        return False
    return partition_lhs >= partition_rhs*0.99


def partition(lhs_set, df, partitions):
    """
    Returns the number of equivilence classes for columns in lhs_set.
    """
    part = partitions.get_partition(lhs_set)
    if part is not None:
        return part
    attrs = df.columns
    attr_cols = [attrs[x] for x in lhs_set]
    df_new = df.drop_duplicates(attr_cols)
    partitions.add_partition(lhs_set, df_new.shape[0])
    return df_new.shape[0]


# def approximate_dependencies(lhs_set, rhs, df, accuracy):

#     # use partitions somehow
#     attrs = df.columns
#     attrs_one = [attrs[x] for x in lhs_set]
#     attrs_two = attrs_one + [attrs[rhs]]

#     df_one = df.drop_duplicates(attrs_one)
#     df_two = df.drop_duplicates(attrs_two)

#     acc = 0
#     limit = df.shape[0]*(1-accuracy)
#     print("this is the  limit")
#     print(limit)


#     while df_one.shape[0] != df_two.shape[0]:
#         merged = df_one.merge(df_two, indicator=True, how='outer')
#         indicator = merged[merged['_merge'] == 'right_only']
#         print(indicator)
#         acc += indicator.shape[0]

#         if acc > limit:
#             return False

#         df_new = df.drop(indicator.index)
#         df_two = df_new.drop_duplicates(attrs_two)

#     return True

class Masks(object):

    def __init__(self, columns):
        self._masks = {}
        for col in columns:
            self._masks[col] = {}

    def add_mask(self, col, val, mask):
        self._masks[col][val] = mask

    def get_mask(self, col, val):
        if val in self._masks[col]:
            return self._masks[col][val]


def approximate_dependencies(lhs_set, rhs, df, accuracy, masks):
    attrs = df.columns
    attrs_one = [attrs[x] for x in lhs_set]
    attrs_two = attrs_one + [attrs[rhs]]

    df_one = df.drop_duplicates(attrs_one)
    df_two = df.drop_duplicates(attrs_two)

    if df_one.shape[0] == df_two.shape[0]:
        return True
    # make this an argument for user, to control how many repeating values
    if df_one.shape[0] > df.shape[0]*.85:
        return False

    acc = 0
    limit = df.shape[0]*(1-accuracy)

    if df_two.shape[0] - df_one.shape[0] > limit:
        return False

    merged = df_one.merge(df_two, indicator=True, how='outer')
    indicator = merged[merged['_merge'] == 'right_only']

    for index, row in indicator.iterrows():
        # options = df
        # for attr in attrs_one:
        #     mask = masks.get_mask(attr, row[attr])

        #     if mask is None:
        #         mask = options[attr].values == row[attr]
        #         masks.add_mask(attr, row[attr], mask)

        #     options = options[mask]

        mask = df[attrs_one[0]].values == row[attrs_one[0]]
        for attr in attrs_one[1:]:
            m = masks.get_mask(attr, row[attr])
            if m is None:
                m = df[attr].values == row[attr]
                masks.add_mask(attr, row[attr], m)
            mask = mask & m

        options = df[mask]

        np = options[attrs[rhs]].to_numpy()
        _, unique_counts = numpy.unique(np, return_counts=True)

        tot = 0
        max_counts = 0
        for size in unique_counts:
            max_counts = max(max_counts, size)
            tot += size

        acc += tot - max_counts
        if acc > limit:
            return False

    # try using numpy arrays and taking intersections of sets for each column????
    return True