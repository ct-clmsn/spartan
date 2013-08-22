#!/usr/bin/env python

from . import prims, distarray, extent, tile
from spartan import util
import numpy as np

def largest_value(vals):
  return sorted(vals, key=lambda v: np.prod(v.shape))[-1]

def eval_Value(ctx, prim):
  return prim.value

def eval_Map(ctx, prim):
  inputs = [evaluate(ctx, v) for v in prim.inputs]
  largest = largest_value(inputs)
  map_fn = prim.map_fn
  
  #@util.trace_fn
  def mapper(ex, tile):
    slc = ex.to_slice()
    local_values = [input[slc] for input in inputs]
    result = map_fn(*local_values)
    assert isinstance(result, np.ndarray), result
    return [(ex, result)]
  
  return largest.map(mapper)


def eval_Reduce(ctx, prim):
  input_array = evaluate(ctx, prim.input)
  dtype = prim.dtype_fn(input_array)
  axis = prim.axis
  shape = extent.shape_for_reduction(input_array.shape, prim.axis)
  tile_accum = tile.TileAccum(prim.combiner_fn)
  output_array = distarray.DistArray.create(ctx, shape, dtype, accum=tile_accum)
  local_reducer = prim.local_reducer_fn
  
  def mapper(ex, tile):
    reduced = local_reducer(ex, tile)
    dst_extent = extent.index_for_reduction(ex, axis)
    output_array.update(dst_extent, reduced)
  
  input_array.foreach(mapper)
  
  return output_array
  

def _evaluate(ctx, prim):
  return globals()['eval_' + prim.typename()](ctx, prim)    
    

def evaluate(ctx, prim):
  assert isinstance(prim, prims.Primitive), 'Not a primitive: %s' % prim
  util.log('Evaluating: %s', prim)
  if prim.cached_value is None:
    prim.cached_value = _evaluate(ctx, prim)
  
  return prim.cached_value