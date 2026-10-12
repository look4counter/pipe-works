"""Execute library-independent TorchScript models on CUDA."""

import torch

from pipeworks.yolo_backend import validate_module_gpu


class TorchScriptBackend:
    def __init__(self, model_path, gpu_id):
        self.model = torch.jit.load(
            str(model_path), map_location=torch.device("cuda", gpu_id)
        ).eval()
        validate_module_gpu(self.model, gpu_id)
        self.scalar_constants = set()
        for module in self.model.modules():
            for method in module._c._method_names():
                self._graph_constants(module._c._get_method(method).graph)

    def _graph_constants(self, graph):
        for node in graph.nodes():
            if node.kind() == "prim::Constant":
                value = node.output().toIValue()
                if (
                    isinstance(value, torch.Tensor)
                    and value.ndim == 0
                    and value.is_cuda
                ):
                    self.scalar_constants.add(value.data_ptr())
            for block in node.blocks():
                self._graph_constants(block)

    def infer(self, inputs):
        if isinstance(inputs, dict):
            return self.model(**inputs)
        return self.model(inputs)
