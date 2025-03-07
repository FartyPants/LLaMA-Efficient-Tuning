import torch
from typing import Dict, Sequence, Union

from .data_collator import DynamicDataCollatorWithPadding

from .peft_trainer import PeftTrainer

from .other import get_logger

logger = get_logger(__name__)


class PairwiseDataCollatorWithPadding(DynamicDataCollatorWithPadding):
    r"""
    Data collator for pairwise data.
    """

    def __call__(self, features: Sequence[Dict[str, Union[torch.Tensor, Sequence[int]]]]) -> Dict[str, torch.Tensor]:
        r"""
        Pads batched data to the longest sequence in the batch.

        We generate 2 * n examples where the first n examples represent chosen examples and
        the last n examples represent rejected examples.
        """
        features = [{"input_ids": feature[key]} for key in ("accept_ids", "reject_ids") for feature in features]
        return super().__call__(features)


class PairwisePeftTrainer(PeftTrainer):
    r"""
    Inherits PeftTrainer to compute pairwise loss.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_return_loss = True # override property to return eval_loss

    def compute_loss(self, model, inputs, return_outputs=False):
        r"""
        Computes pairwise loss. The first n examples are chosen and the last n examples are rejected.

        We use score on the EOS token to represent reward of the whole sentence.

        Subclass and override to inject custom behavior. It should not be directly used by external scripts.
        """
        batch_size = inputs["input_ids"].size(0) // 2
        _, _, values = model(**inputs)
        r_accept, r_reject = values[:, -1].split(batch_size, dim=0)
        loss = -torch.log(torch.sigmoid(r_accept - r_reject)).mean()
        outputs = {"r_accept": r_accept, "r_reject": r_reject}
        return (loss, outputs) if return_outputs else loss
