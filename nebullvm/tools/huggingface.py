from collections import OrderedDict
from typing import (
    Union,
    Iterable,
    List,
    Dict,
    Tuple,
    Type,
    Any,
)

import numpy as np

from nebullvm.optional_modules.torch import torch, Module
from nebullvm.tools.base import Device

try:
    from transformers import (
        PreTrainedModel,
    )
    from transformers.tokenization_utils import PreTrainedTokenizer
except ImportError:
    # add placeholders for function definition
    PreTrainedModel = None
    PreTrainedTokenizer = None


class TransformerWrapper(Module):
    """Class for wrappering the Transformers and give them an API compatible
    with nebullvm. The class takes and input of the forward method positional
    arguments and transform them in the input dictionaries needed by
    transformers classes. At the end it also flattens their output.
    """

    def __init__(
        self,
        core_model: Module,
        encoded_input: Dict[str, torch.Tensor],
    ):
        super().__init__()
        self.core_model = core_model
        self.inputs_types = OrderedDict()
        for key, value in encoded_input.items():
            self.inputs_types[key] = value.dtype

    def forward(self, *args: torch.Tensor):
        inputs = {
            key: value for key, value in zip(self.inputs_types.keys(), args)
        }
        outputs = self.core_model(**inputs)
        outputs = outputs.values() if isinstance(outputs, dict) else outputs
        return tuple(flatten_outputs(outputs))


def flatten_outputs(
    outputs: Union[torch.Tensor, Iterable]
) -> List[torch.Tensor]:
    new_outputs = []
    for output in outputs:
        if isinstance(output, torch.Tensor):
            new_outputs.append(output)
        else:
            flatten_list = flatten_outputs(output)
            new_outputs.extend(flatten_list)
    return new_outputs


def get_size_recursively(
    tensor_tuple: Union[torch.Tensor, Tuple]
) -> List[int]:
    if isinstance(tensor_tuple[0], torch.Tensor):
        return [len(tensor_tuple)]
    else:
        inner_size = get_size_recursively(tensor_tuple[0])
        return [len(tensor_tuple), *inner_size]


def get_output_structure_from_text(
    text: str,
    model: PreTrainedModel,
    tokenizer: PreTrainedTokenizer,
    tokenizer_args: Dict,
    device: Device,
) -> Tuple[OrderedDict, Type]:
    """Function needed for saving in a dictionary the output structure of the
    transformers model.
    """
    device = torch.device("cuda" if device is Device.GPU else "cpu")
    encoded_input = tokenizer([text], **tokenizer_args).to(device)
    output = model(**encoded_input)
    structure = OrderedDict()
    if isinstance(output, tuple):
        for i, value in enumerate(output):
            if isinstance(value, torch.Tensor):
                structure[f"output_{i}"] = None
            else:
                size = get_size_recursively(value)
                structure[f"output_{i}"] = size
    else:
        for key, value in output.items():
            if isinstance(value, torch.Tensor):
                structure[key] = None
            else:
                size = get_size_recursively(value)
                structure[key] = size
    return structure, type(output)


def get_output_structure_from_dict(
    input_example: Dict,
    model: PreTrainedModel,
    device: Device,
) -> Tuple[OrderedDict, Type]:
    """Function needed for saving in a dictionary the output structure of the
    transformers model.
    """
    device = torch.device("cuda" if device is Device.GPU else "cpu")
    input_example.to(device)
    model.to(device)
    output = model(**input_example)
    structure = OrderedDict()
    if isinstance(output, tuple):
        for i, value in enumerate(output):
            if isinstance(value, torch.Tensor):
                structure[f"output_{i}"] = None
            else:
                size = get_size_recursively(value)
                structure[f"output_{i}"] = size
    else:
        for key, value in output.items():
            if isinstance(value, torch.Tensor):
                structure[key] = None
            else:
                size = get_size_recursively(value)
                structure[key] = size
    return structure, type(output)


def restructure_output(
    output: Tuple[torch.Tensor],
    structure: OrderedDict,
    output_type: Any = None,
):
    """Restructure the flatter output using the structure dictionary given as
    input.
    """
    output_dict = {}
    idx = 0
    for key, value in structure.items():
        if value is None:
            output_dict[key] = output[idx]
            idx += 1
        else:
            tensor_shape = output[idx].shape[1:]
            output_dict[key] = list(
                torch.reshape(
                    torch.stack(
                        output[idx : int(np.prod(value)) + idx]  # noqa E203
                    ),
                    (*value, *tensor_shape),
                )
            )
            idx += np.prod(value)
    if output_type is not None:
        return output_type(**output_dict)
    return output_dict
