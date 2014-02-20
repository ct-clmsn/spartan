'''
Reshape operation and expr.
'''

import numpy as np
import scipy.sparse as sp
from spartan import rpc
from .base import Expr, lazify
from .. import blob_ctx, util
from ..node import Node, node_type
from ..util import is_iterable, Assert
from ..array import extent, tile, distarray
from ..core import LocalKernelResult
from .shuffle import target_mapper

class Reshape(distarray.DistArray):
  '''Reshape the underlying array base.

  Reshape does not create a copy of the base array. Instead the fetch
  method is overridden:
  1. Caculate the underlying extent containing the requested extent.
  2. Fetch the underlying extent.
  3. Trim the fetched tile and reshape to the requested tile.
  '''

  def __init__(self, base, shape):
    Assert.isinstance(base, distarray.DistArray)
    self.base = base
    self.shape = shape
    self.dtype = base.dtype
    self.sparse = self.base.sparse
    self.bad_tiles = []

  def fetch(self, ex):
    ravelled_ul = extent.ravelled_pos(ex.ul, ex.array_shape)
    ravelled_lr = extent.ravelled_pos([lr - 1 for lr in ex.lr], ex.array_shape)

    (base_ravelled_ul, base_ravelled_lr) = extent.find_rect(ravelled_ul, ravelled_lr, self.base.shape)

    base_ul = extent.unravelled_pos(base_ravelled_ul, self.base.shape)
    base_lr = extent.unravelled_pos(base_ravelled_lr, self.base.shape)
    base_ex = extent.create(base_ul, np.array(base_lr) + 1, self.base.shape)

    (rect_ravelled_ul, rect_ravelled_lr) = extent.find_rect(base_ravelled_ul, base_ravelled_lr, self.base.shape)

    rect_ul = extent.unravelled_pos(rect_ravelled_ul, self.base.shape)
    rect_lr = extent.unravelled_pos(rect_ravelled_lr, self.base.shape)
    rect_ex = extent.create(rect_ul, np.array(rect_lr) + 1, self.base.shape)

    if not self.base.sparse:
      tile = np.ravel(self.base.fetch(rect_ex))
      tile = tile[(base_ravelled_ul - rect_ravelled_ul):(base_ravelled_lr - rect_ravelled_ul) + 1]
      return tile.reshape(ex.shape)
    else:
      tile = self.base.fetch(rect_ex)
      new = sp.lil_matrix(ex.shape, dtype=self.base.dtype)
      j_max = tile.shape[1]
      for i,row in enumerate(tile.rows):
        for col,j in enumerate(row):
          rect_index = i*j_max + j
          target_start = base_ravelled_ul - rect_ravelled_ul
          target_end = base_ravelled_lr - rect_ravelled_ul
          if rect_index >= target_start and rect_index <= target_end:
            new_r,new_c = np.unravel_index(rect_index - target_start, ex.shape)
            new[new_r,new_c] = tile[i,j]
      return new

@node_type
class ReshapeExpr(Expr):
  _members = ['array', 'new_shape', 'tile_hint']

  def __str__(self):
    return 'Reshape[%d] %s to %s' % (self.expr_id, self.expr, self.new_shape)

  def _evaluate(self, ctx, deps):
    v = deps['array']
    shape = deps['new_shape']
    return Reshape(v, shape)

def reshape(array, new_shape, tile_hint=None):
  '''
  Reshape/retile ``array``.

  Returns a ReshapeExpr with the given shape.

  :param array: `Expr`
  :param new_shape: `tuple`
  :param tile_hint: `tuple` or None
  '''

  Assert.isinstance(new_shape, tuple)
  array = lazify(array)

  return ReshapeExpr(array=array,
                     new_shape=new_shape,
                     tile_hint=tile_hint)

