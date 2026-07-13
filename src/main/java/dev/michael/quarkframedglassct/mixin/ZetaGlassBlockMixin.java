package dev.michael.quarkframedglassct.mixin;

import dev.michael.quarkframedglassct.FramedGlassGroup;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.state.BlockState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(targets = "org.violetmoon.zeta.block.ZetaGlassBlock", remap = false)
public abstract class ZetaGlassBlockMixin {
    @Inject(method = "skipRendering", at = @At("HEAD"), cancellable = true, remap = false)
    private void quarkFramedGlassCt$skipCrossColorFace(
        BlockState state,
        BlockState adjacentState,
        Direction side,
        CallbackInfoReturnable<Boolean> callback
    ) {
        if (FramedGlassGroup.contains(state.getBlock()) && FramedGlassGroup.contains(adjacentState.getBlock())) {
            callback.setReturnValue(true);
        }
    }
}
