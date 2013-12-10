#!/usr/bin/env python

import collections

from .. import util, blob_ctx
from ..array import distarray
from .local import LocalCtx, make_var, LocalInput, LocalMapExpr
from ..node import Node
from spartan.expr import local
from ..util import Assert
from .base import DictExpr, Expr, as_array

def tile_mapper(ex, children, op):
  ctx = blob_ctx.get()
  #util.log_info('MapTiles: %s', map_fn)
  #util.log_info('Fetching %d inputs', len(children))
  #util.log_info('%s %s', children, ex)

  local_values = dict([(k, v.fetch(ex)) for (k, v) in children.iteritems()])
  op_ctx = LocalCtx(inputs=local_values)

  #util.log_info('Inputs: %s', local_values)
  result = op.evaluate(op_ctx)
  #util.log_info('Result: %s', result)
  Assert.eq(ex.shape, result.shape, 'Bad shape: (%s)' % op)
  return [(ex, result)]


class MapExpr(Expr):
  __metaclass__ = Node
  _members = ['children', 'op']

  def compute_shape(self):
    '''MapTiles retains the shape of inputs.

    Broadcasting results in a map taking the shape of the largest input.
    '''
    shapes = [i.shape for i in self.children.values()]
    output_shape = collections.defaultdict(int)
    for s in shapes:
      for i, v in enumerate(s):
        output_shape[i] = max(output_shape[i], v)
    return tuple([output_shape[i] for i in range(len(output_shape))])

  def evaluate(self, ctx, deps):
    children = deps['children']
    op = self.op

    #for c in children:
    #  util.log_info('Child: %s', c)

    print local.codegen(op)

    keys = children.keys()
    vals = children.values()
    vals = distarray.broadcast(vals)
    largest = distarray.largest_value(vals)

    children = dict(zip(keys, vals))
    #util.log_info('Mapping %s over %d inputs; largest = %s', op, len(children), largest.shape)

    result = largest.map_to_array(tile_mapper,
                                  kw = { 'children' : children,
                                         'op' : op })
    return result

def map(inputs, fn, numpy_expr=None):
  '''
  Evaluate ``fn`` over each tile of the input.
  :param v: `Expr`
  :param fn: callable taking arguments ``*inputs``
  '''
  if not util.iterable(inputs):
    inputs = [inputs]

  if numpy_expr is None:
    numpy_expr = fn.__name__

  op_deps = []
  children = {}
  for v in inputs:
    v = as_array(v)
    varname = make_var()
    children[varname] = v
    op_deps.append(LocalInput(idx=varname))

  children = DictExpr(vals=children)
  op = LocalMapExpr(fn=fn,
             pretty_fn=numpy_expr,
             deps=op_deps)

  return MapExpr(children=children, op=op)


