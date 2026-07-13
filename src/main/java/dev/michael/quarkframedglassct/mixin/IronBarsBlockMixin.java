package dev.michael.quarkframedglassct.mixin;

import dev.michael.quarkframedglassct.FramedGlassGroup;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.IronBarsBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(IronBarsBlock.class)
public abstract class IronBarsBlockMixin {
    @Inject(method = "skipRendering", at = @At("HEAD"), cancellable = true)
    private void quarkFramedGlassCt$skipCrossColorPaneFace(
        BlockState state,
        BlockState adjacentState,
        Direction side,
        CallbackInfoReturnable<Boolean> callback
    ) {
        if (!FramedGlassGroup.containsPane(state.getBlock()) || !FramedGlassGroup.containsPane(adjacentState.getBlock())) {
            return;
        }
        if (!side.getAxis().isHorizontal()) {
            callback.setReturnValue(true);
            return;
        }
        BooleanProperty ownSide = property(side);
        BooleanProperty adjacentSide = property(side.getOpposite());
        if (state.getValue(ownSide) && adjacentState.getValue(adjacentSide)) {
            callback.setReturnValue(true);
        }
    }

    private static BooleanProperty property(Direction direction) {
        return switch (direction) {
            case NORTH -> BlockStateProperties.NORTH;
            case EAST -> BlockStateProperties.EAST;
            case SOUTH -> BlockStateProperties.SOUTH;
            case WEST -> BlockStateProperties.WEST;
            default -> throw new IllegalArgumentException("Expected horizontal direction, got " + direction);
        };
    }
}
