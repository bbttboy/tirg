
# TODO(lujiang): put it into the third-party
# MIT License

# Copyright (c) 2018 Nam Vo

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

"""Metric learning functions.

Codes are modified from:
https://github.com/lugiavn/generalization-dml/blob/master/nams.py
"""

import numpy as np
import torch
import torchvision


def pairwise_distances(x, y=None):
  """
    Input: x is a Nxd matrix
           y is an optional Mxd matirx
    Output: dist is a NxM matrix where dist[i,j] is the square norm between
    x[i,:] and y[j,:]
            if y is not given then use 'y=x'.
    i.e. dist[i,j] = ||x[i,:]-y[j,:]||^2
    source:
    https://discuss.pytorch.org/t/efficient-distance-matrix-computation/9065/2
    """
  x_norm = (x**2).sum(1).view(-1, 1)
  if y is not None:
    y_t = torch.transpose(y, 0, 1)
    y_norm = (y**2).sum(1).view(1, -1)
  else:
    y_t = torch.transpose(x, 0, 1)
    y_norm = x_norm.view(1, -1)

  dist = x_norm + y_norm - 2.0 * torch.mm(x, y_t)
  # Ensure diagonal is zero if x=y
  # if y is None:
  #     dist = dist - torch.diag(dist.diag)
  return torch.clamp(dist, 0.0, np.inf)


class MyTripletLossFunc(torch.autograd.Function):

  @staticmethod
  def random_triplets(features):
    size = features.shape[0]

    triplets = []
    labels = list(range(int(size / 2))) + list(range(int(size / 2)))
    for i in range(len(labels)):
      triplets_i = []
      for j in range(len(labels)):
        if labels[i] == labels[j] and i != j:
          for k in range(len(labels)):
            if labels[i] != labels[k]:
              triplets_i.append([i, j, k])
      np.random.shuffle(triplets_i)
      triplets += triplets_i[:3]
    assert (triplets and len(triplets) < 2000)
    return triplets

  @staticmethod
  def forward(ctx, features):

    distances = pairwise_distances(features).cpu().numpy()
    triplets = MyTripletLossFunc.random_triplets(features)

    loss = 0.0
    triplet_count = 0.0
    correct_count = 0.0
    for i, j, k in triplets:
      w = 1.0
      triplet_count += w
      loss += w * np.log(1 + np.exp(distances[i, j] - distances[i, k]))
      if distances[i, j] < distances[i, k]:
        correct_count += 1

    loss /= triplet_count

    triplet_count = torch.autograd.Variable(torch.FloatTensor([triplet_count]))
    distances = torch.autograd.Variable(torch.FloatTensor(distances))
    triplets = torch.autograd.Variable(torch.FloatTensor(triplets))
    ctx.save_for_backward(features, triplets, triplet_count, distances)

    return torch.FloatTensor((loss,))

  @staticmethod
  def backward(ctx, grad_output):
    features, triplets, triplet_count, distances = ctx.saved_tensors
    features_np = features.cpu().numpy()
    grad_features = features.clone() * 0.0
    grad_features_np = grad_features.cpu().numpy()

    for i, j, k in triplets:
      i = int(i.item())
      j = int(j.item())
      k = int(k.item())
      w = 1.0
      f = 1.0 - 1.0 / (1.0 + np.exp(distances[i, j] - distances[i, k]))
      grad_features_np[i, :] += (w * f * (features_np[i, :] - features_np[j, :]) / triplet_count).numpy()
      grad_features_np[j, :] += (w * f * (features_np[j, :] - features_np[i, :]) / triplet_count).numpy()
      grad_features_np[i, :] += (-w * f * (features_np[i, :] - features_np[k, :]) / triplet_count).numpy()
      grad_features_np[k, :] += (-w * f * (features_np[k, :] - features_np[i, :]) / triplet_count).numpy()

    for i in range(features_np.shape[0]):
      grad_features[i, :] = torch.from_numpy(grad_features_np[i, :])
    grad_features *= float(grad_output.data[0])
    return grad_features


class TripletLoss(torch.nn.Module):
  """Class for the triplet loss."""
  def __init__(self, pre_layer=None):
    super(TripletLoss, self).__init__()
    self.pre_layer = pre_layer

  def forward(self, x):
    if self.pre_layer is not None:
      x = self.pre_layer(x)
    loss = MyTripletLossFunc.apply(x)
    return loss


class NormalizationLayer(torch.nn.Module):
  """Class for normalization layer."""
  def __init__(self, normalize_scale=1.0, learn_scale=True):
    super(NormalizationLayer, self).__init__()
    self.norm_s = float(normalize_scale)
    if learn_scale:
      self.norm_s = torch.nn.Parameter(torch.FloatTensor((self.norm_s,)))

  def forward(self, x):
    features = self.norm_s * x / torch.norm(x, dim=1, keepdim=True).expand_as(x)
    return features
