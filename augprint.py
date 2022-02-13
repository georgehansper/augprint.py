#!/usr/bin/python3
# vim: smarttab:expandtab:shiftwidth=4:tabstop=4:softtabstop=4

import sys
from pprint import pprint, pformat
import json
import argparse
import re

sys.path.insert(0,'/home/george/github/python-augeas') 
#pprint(sys.path)
import augeas

def printv(mesg):
  global args
  if args.verbose or args.debug:
    if isinstance(mesg,list) or isinstance(mesg,dict):
      print(json.dumps(mesg, indent=2, sort_keys=True),file=sys.stderr)
    elif isinstance(mesg,str) or isinstance(mesg,int):
      print(mesg,file=sys.stderr)
    else:
      #print(pformat(mesg, width=120, sort_dicts=False), file=sys.stderr)
      print(pformat(mesg, width=120), file=sys.stderr)

def print_debug(mesg):
  global args
  if args.debug:
    if isinstance(mesg,list) or isinstance(mesg,dict):
      print(json.dumps(mesg, indent=2, sort_keys=True),file=sys.stderr)
    elif isinstance(mesg,str) or isinstance(mesg,int):
      print(mesg,file=sys.stderr)
    else:
      #print(pformat(mesg, width=120, sort_dicts=False), file=sys.stderr)
      print(pformat(mesg, width=120), file=sys.stderr)

escaped_chars_q = str.maketrans( {
        '\'': '\\\'',
        '\\': '\\\\',
        "\n": '\\n',
        "\t": '\\t',
        } )

escaped_chars_qq = str.maketrans( {
        '"': '\\"',
        '\\': '\\\\',
        "\n": '\\n',
        "\t": '\\t',
        } )

aug = augeas.Augeas(flags=augeas.Augeas.NO_LOAD)
#aug = augeas.Augeas()

'''
augprint.py will print the complete set of paths for a give file, in a way
that is intended to be idempotent.

    * If the path already exists but has a different value, the value is reset
    * If the path does not exist, it is created and the value is assigned
    * If the path already exists, and it has the same value, then no change it made.

In practise, this means that the output from augprint.py can be re-applied over and over
to the same file, and no further modifications occur after the first time.

The output differs from that of the augtool 'print' command in that:

    * numbered positions in the path are replaced by filter-expressions
    * paths are prefixed with the 'set' keyword
    * there is no '=' inserted between the path and the value

This allow the output from this command to use directly with augtool to
bring a file into a desired state
'''

parser = argparse.ArgumentParser(description='''
Print a complete list of augtool 'set' commands that correspond to a given filename
''')
parser.add_argument('--verbose','-v', action='store_const', const=True, default=False,
                    help='Print verbose output')
parser.add_argument('--debug','-d', action='store_const', const=True, default=False,
                    help='Print debugging output')
parser.add_argument('--lens',type=str, action='store', dest='lens', default=None,
                     help='Name of augeas lens to use')
parser.add_argument('filename',type=str, action='store', nargs='?', default='/etc/hosts',
                    help='file to process')
parser.add_argument('--seq','-s', action='store', dest='seq', default='y',
                    help='Generate expressions .../seq::*[expr] for numbered nodes Y/n')

args = parser.parse_args()

# Choose the wildcard operator for numbered nodes - important because '+' is idempotent if available
numwild = '*'
if not ( args.seq.lower() == 'n' or args.seq.lower() == 'no'):
    numwild = 'seq::*'

print_debug(args)

# yyy(?=abc) non-consuming look-ahead (?:abc) non-capturing parenthesis (?<=abc)def non-consuming look-behind
split_re = re.compile('(?<=/)(?:([-0-9a-zA-Z_#]+)\[([0-9]+)\]|([0-9]+))(?:(?=/)|$)')

filename = args.filename

lens = args.lens
if lens is not None:
    path_lens_incl = '/augeas/load/%s/incl[0]' % lens
    aug.set(path_lens_incl, filename)
    try:
        aug.load_file(filename)
    except RuntimeError as e:
        print(e)
        sys.exit(1)
    print("set %s  '%s'" % (path_lens_incl, filename))
else:
    try:
        aug.load_file(filename)
    except RuntimeError as e:
        # If there is no lens for this file, try again with Simplelines
        pass
    lens = aug.get('/augeas/files' + filename + '/lens')
    # Was there a default lens for this file?
    if len(aug.match('/files' + filename)) == 0:
        lens = 'Simplelines'
        # No, lets just use Simplelines instead
        print("# Warning: no lens for file %s\n# Warning: using lens Simplelines" % (filename))
        path_lens_incl = '/augeas/load/%s/incl[0]' % lens
        aug.set(path_lens_incl, filename)
        try:
            aug.load_file(filename)
        except RuntimeError as e:
            print(e)
            sys.exit(1)

if lens:
    lens = lens.lstrip('@')
    printv('Processing file %s using lens %s' % (filename, lens))
else:
    print('No lens found for file: ' + filename, file=sys.stderr)
    sys.exit(1)


print("load-file %s" % (filename))

# Given:
# /files/some/path/label[1]/tail_a    value_1_a  <- potentially unique head/tail/value combination
# /files/some/path/label[1]/tail_b    value_1_b
# /files/some/path/label[2]/tail_a    value_2_a
# /files/some/path/label[2]/tail_b    value_2_b
#
# First we group all paths together that have
#   /files/some/path/ [ label ]
#
#  path_group['/files/some/path/'+'label'] = dict()
#
# We create an index for each numbered subtree
#   1, 2, 3, 4...
#
# And keep a list (hash) of each tail+value in each numbered subtree
#
# path_group[/files/some/path/'+'label'][1] = { tail_a: value_1_a, tail_b: value_1_b ]
# 
# With python3, the insertion order is preserved, but we still lose the original 'list' structure of the tree
# Paths are grouped by number and tail, which destroys the original order
#
# Second, we scan the numbered subtrees, looking for a tail_X value which:
# a) Is present in all subtrees
# b) Has a unique value in each subtree (eg value_1_a != value_2_a)
# c) Unless tail_X is the first entry, an empty value is not permitted ???
#
# Instead of 'scanning' we maintain an inverted structure, where the numbered indexes are listed per-head-label-tail-value
#
#   path_group_tail_value[ '/files/some/path/'+'label' ][ 'tail_a' ] = { 'value_1_a': [1], 'value_2_a': [2] }
#                                                                                      ^
#                                              list of subtrees with the same value ---'
#
# And another similar one, for ensuring that a 'tail' is present in each numbered group
#
#   path_group_tail_num[ '/files/some/path/'+'label' ][ 'tail_a' ] = { 1: 'value_1_a', 2: 'value_2_a' }
#                                                          ^---path_group_tail
#
# To choose a 'tail' we iterate over the [num] entries, and examine path_group_tails, looking for the first
# 'tail' to represent a 'complete set'. As a short-cut, we use 'len()' to compare the number of entries.
#
# BUT the set does not need to be complete, just unique...see squid.conf example:
#
#
# Special case - squid.conf, where value is not unique, but tail is, eg:
# 
# /files/etc/squid/squid.conf/acl[2]/localnet/setting = "10.0.0.0/8"
# /files/etc/squid/squid.conf/acl[3]/localnet/setting = "100.64.0.0/10"
# /files/etc/squid/squid.conf/acl[9]/SSL_ports/setting = "443"
# /files/etc/squid/squid.conf/acl[12]/Safe_ports/setting = "443"
#  ... relax the 'chosen_tail' criteria (a) 
#      the chosen tail needs to be present in a subset of the group _and_ unique within the subset
#
#  a) Scan tails for a given path_group (.../acl), result is: localnet/setting  SSL_port/setting  Safe_ports/setting
#  b) Across all possible groups (num), look for the first tail for each [num] that
#     - has a unique value for all [num] entries where it exists
#     - note the tail with the first non-null 'value' for the [num] group (first_tail)
#      group tails - look for unique tails, and apply the criteria to unique tails
#      tail must be either:
#          unique to that group - single chosen_tail result
#          or have unique values across all groups where present
#          This would result in an array of chosen_tail values for a group but that's OK, because 
#          we can 'pick' the tail which is appropriate to this path
#
#
# Last, we write a path-expression, in the form of:
#
#   set /files/some/path/label[tail_a = value_1_a]/tail_a   value_1_a


class pathClass:
    # This re will is used to split a path:
    # /some/path/label[1]/morepath/5/tail
    # into an array:
    # ['/some/path/', 'label', '1', None, '/morepath/', None, None, '5', '/tail']
    # ie. both label[1] and 5 generate 3x list-elements each
    # (?<=/)   "look-before" ie. expression must be preceeded by '/'
    # (?=/)    "look-ahead"  ie. expression mush be followed by '/'
    # (?:text) like ( ) but don't consume or capture text
    split_re = re.compile('(?<=/)(?:([-0-9a-zA-Z_#]+)\[([0-9]+)\]|([0-9]+))(?:(?=/)|$)')
    groups = []         # probably don't need to save this here...
    def __init__(self, ndx, path, value):
        self.ndx = ndx
        self.path = path
        self.value = value
        self.segments = split_re.split(path)
        self.path_has_tail = dict()
        #print_debug(self.segments)
        # eg if path is /files/etc/hosts/2/alias[1]
        # segments is an array of [ /files/etc, None, None, 2, /, alias, 1, None, '' ]

    def split(self):
        ii=0
        head = ''
        self.groups = []
        while ii < len(self.segments)-1:
            head += self.segments[ii]
            if self.segments[ii+1] is None:
                label = numwild
                num   = self.segments[ii+3]
                head_append = num
            else:
                label = self.segments[ii+1]
                num   = self.segments[ii+2]
                head_append = '%s[%s]' % ( label, num )

            tail =''
            for jj in range(ii+4, len(self.segments), 4):
                tail += self.segments[jj]
                if jj < len(self.segments)-1:
                    tail += ( self.segments[jj+1] or numwild )
            self.groups.append([head+label, label, num, tail, self.value])
            self.path_has_tail[tail.lstrip('/')] = 1
            #print_debug("head+label: %-20s ndx: %s  tail: %s  value: %s" % (head+label, ndx, tail, str(self.value)))
            #print_debug(result[-1])
            head += head_append
            ii += 4
        return self.groups

# An instance of this class exist for every 'head'
# The class consists of
#  - num ... the position or 'number' of all child nodes
#  - tail ... the simplified path to an actual value
#  - value ... the value of the child node
class groupClass:

    def __init__(self):
        self.num_tail_value = dict()
        self.has_tail = dict()
        self.has_value = dict()
        self.chosen_tail = None
        self.num_first_tail = dict()

    def add(self, num, tail, value, path_ndx):
        #if tail == '' and value is None:
        #    return
        #if value is None:
            # Ignore the 'directories' (intermediate node) with a value of None
            # Ignore empty values
        #    return
        tail = tail.lstrip('/')
        if num not in self.num_tail_value:
            self.num_tail_value[num] = dict()
            self.num_first_tail[num] = tail
        if tail not in self.num_tail_value[num]:
            self.num_tail_value[num][tail] = []
        if tail not in self.has_tail:
            self.has_tail[tail] = dict()
        if tail not in self.has_value:
            self.has_value[tail] = dict()
        if value not in self.has_value[tail]:
            self.has_value[tail][value] = []

        self.num_tail_value[num][tail].append(value)
        self.has_tail[tail][num] = 1
        self.has_value[tail][value].append(num)

    def count(self):
        return(len(self.num_tail_value))

    # Once all the entries have been added to this object, we can use 'choose_tail' to select
    # the first tail that has a unique value across all possible 'num' entries
    def choose_tail(self):
        print_debug("choose_tail() -------")
        print_debug(pformat(self.has_tail, width=140))
        print_debug(pformat(self.num_tail_value, width=140))
        # Find a tail for each 'num' that is has a unique values from other 'num' values where it exists
        tail_with_unique_values=dict()
        for tail in self.has_tail:
            print_debug('choose_tail() tail: '+tail)
            # work backwards - eliminate non-unique tails to begin with
            # identify candidate tail ie those which only have unique values
            tail_with_unique_values[tail] = dict()
            for value in self.has_value[tail]:
                if len(self.has_value[tail][value]) == 1:
                    num = self.has_value[tail][value][0]
                    tail_with_unique_values[tail][num] = 1
        self.chosen_tail = dict()
        #print_debug("choose_tail() tail_with_unique_values[tail][num]")
        #print_debug(tail_with_unique_values)
        self.value_length = 0   # just for pretty formatting
        for num in self.num_tail_value:
            for tail in tail_with_unique_values:
                if num in tail_with_unique_values[tail] and num not in self.chosen_tail:
                    #print_debug('chosen_tail() for num=%s is %s' % (num, tail))
                    self.chosen_tail[num] = tail
                    if self.num_tail_value[num][tail][0] is not None:
                        vlen = len(self.num_tail_value[num][tail][0])
                        if vlen > self.value_length:
                            self.value_length = vlen

        print_debug("choose_tail() chosen_tail: ")
        print_debug(self.chosen_tail)
        return self.chosen_tail

    def chosen_value(self, num):
        if isinstance(self.chosen_tail, str):
            value = self.num_tail_value[num][self.chosen_tail][0]
        elif num in self.chosen_tail:
            value = self.num_tail_value[num][ self.chosen_tail[num]][0] or num
        else:
            return None
        return value

    def get_chosen_tail(self, num):
        if isinstance(self.chosen_tail, str):
            return self.chosen_tail
        elif isinstance(self.chosen_tail, dict):
            return self.chosen_tail.get(num,None)
        else:
            return None

    def get_first_tail(self, num):
        return self.num_first_tail[num]

all_path_groups = dict()
path_list = []

match = aug.match('/files'+filename+'//*')

for ndx, path in enumerate(match):
    # for each augeas path in the file,
    value = aug.get(path)
    if value is not None:
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        #value = value.translate(escaped_chars)
    else:
        if len(aug.match(path + '/*')) != 0:
            # This is a node with a null value, and has child node(s)
            # We can safely ignore it, as it will be create if/when the child node(s) are created
            continue

    pathObj = pathClass(ndx,path,value)
    path_list.append(pathObj)
    path_groups = pathObj.split()
    for (head, label, num, tail, value) in path_groups:
        if head not in all_path_groups:
          all_path_groups[head] = groupClass()
        all_path_groups[head].add( num, tail, value, ndx)

for head in all_path_groups:
    print_debug("\n---")
    print_debug("head: " + head)
    print_debug("group: ")
    print_debug(all_path_groups[head])
    print_debug("chosen_tail: " + str(all_path_groups[head].choose_tail()))
#    pprint(all_path_groups[head].chosen_tail)

chosen_tail_created = False
last_num = ''
no_tail_found = dict()      # Paths where we did not find a suitably unique tail
for path_ndx, pathObj in enumerate(path_list):
    #pprint(pathObj.segments)
    #pprint(pathObj.groups)
    print_debug(pathObj.path_has_tail)
    printv("set %s %s" % (pathObj.path, pathObj.value))

    path_out = ''
    path_head = ''
    for ii in range(0, len(pathObj.segments), 4):
        path_out += pathObj.segments[ii]
        path_head += pathObj.segments[ii]
        if ii >= len(pathObj.segments) - 1:
            #pprint('Break: ' + str(ii) +  '  '  + pathObj.path)
            #pprint(pathObj.segments)
            break
        if pathObj.segments[ii+1] is None:
            # path is of the form .../1/...
            num = pathObj.segments[ii+3]
            label = ''
            pos = num
            path_group = path_head + numwild
            path_out += numwild
        else:
            # path is of the form .../label[1]/...
            num = pathObj.segments[ii+2]
            label = pathObj.segments[ii+1]
            pos = '[%s]' % num
            path_group = path_head + label
            path_out += label
        #print_debug(path_group)
        path_head += label + pos
        chosen_tail = all_path_groups[path_group].get_chosen_tail(num)
        first_tail  = all_path_groups[path_group].get_first_tail(num)
        first_tail_value = all_path_groups[path_group].num_tail_value[num][first_tail][0]

        # update ----v
        #if isinstance(chosen_tail,dict):
        #    selected = None
        #    for tail in chosen_tail:
        #        if tail in pathObj.path_has_tail:
        #            selected = tail
        #            break
        #    chosen_tail = selected
        # update ----^

        if num != last_num:
            chosen_tail_created = False
        if chosen_tail is None:
            #print("Warning: no unique filter found for group: %s" % path_group, file=sys.stderr)
            if path_group not in no_tail_found:
                no_tail_found[path_group] = []
            no_tail_found[path_group].append(path_ndx)
            if label == '':
                path_out += "[label() ='%s']" % num
            else:
                path_out += "[position() = %s]" % num
            chosen_tail = first_tail  # Just a starting point for futher manual editting
            chosen_value = first_tail_value
        else:
            chosen_value = all_path_groups[path_group].chosen_value(num)

        # augtool does not allow quotes to be quoted ie ' within '...' or " within "..."
        if isinstance(chosen_value,str):
            if "'" in chosen_value:
                chosen_value = '"' + chosen_value.translate(escaped_chars_qq) + '"'
            else:
                chosen_value = "'" + chosen_value.translate(escaped_chars_q) + "'"

        chosen_tail_or_dot = chosen_tail
        if chosen_tail == '':
            chosen_tail_or_dot = '.'
        print_debug('chosen_tail_or_dot: ' + chosen_tail_or_dot)
        if chosen_tail_created or num != last_num or chosen_tail == first_tail:
            # This is the first path in a group, or we have created the chosen_tail, no qualifing count()=0 required
            path_out += "[%s=%-20s]" % ( chosen_tail_or_dot, chosen_value )
        else:
            # 
            path_out += "[%s=%s or (count(%s)=0 and %s=%s)]" % ( chosen_tail_or_dot, chosen_value, chosen_tail_or_dot, first_tail, first_tail_value)
        if chosen_tail in pathObj.path_has_tail:
            chosen_tail_created = True
        last_num = num
    # Write out the resulting path - special case if path_out has been set to None, skip this path
    # eg:
    # /files/etc/hosts/1   None    <---- want to skip this
    # /files/etc/hosts/1/ipaddr    <---- but only if one of these exists
    print("set %s  '%s'" % (path_out, (pathObj.value or '').translate(escaped_chars_q)))

if len(aug.match('/augeas/version/pathx/functions/modified')) >0:
    print("match /files%s//*[modified()]" % filename )

if no_tail_found:
    print("Warning: no suitably unique tail was found for some paths", file=sys.stderr)
    for path_group in no_tail_found:
        print(path_group, file=sys.stderr)
        for ndx in no_tail_found[path_group]:
            print("    %s" % path_list[ndx].path, file=sys.stderr)
