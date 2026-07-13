package dev.michael.quarkframedglassct.mixin;

import dev.michael.quarkframedglassct.FramedGlassGroup;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.core.Direction;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.client.model.data.ModelData;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(targets = "com.supermartijn642.fusion.model.modifiers.block.PaneCullingBakedModel", remap = false)
public abstract class PaneCullingBakedModelMixin {
    @Redirect(
        method = "getQuads(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/core/Direction;Lnet/minecraft/util/RandomSource;Lnet/neoforged/neoforge/client/model/data/ModelData;Lnet/minecraft/client/renderer/RenderType;)Ljava/util/List;",
        at = @At(
            value = "INVOKE",
            target = "Lnet/minecraft/world/level/block/state/BlockState;getBlock()Lnet/minecraft/world/level/block/Block;",
            ordinal = 0
        ),
        remap = false
    )
    private Block quarkFramedGlassCt$treatPaneAboveAsSame(
        BlockState neighbor,
        BlockState state,
        Direction cullDirection,
        RandomSource random,
        ModelData data,
        RenderType renderType
    ) {
        return groupedBlockOrOriginal(neighbor, state);
    }

    @Redirect(
        method = "getQuads(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/core/Direction;Lnet/minecraft/util/RandomSource;Lnet/neoforged/neoforge/client/model/data/ModelData;Lnet/minecraft/client/renderer/RenderType;)Ljava/util/List;",
        at = @At(
            value = "INVOKE",
            target = "Lnet/minecraft/world/level/block/state/BlockState;getBlock()Lnet/minecraft/world/level/block/Block;",
            ordinal = 2
        ),
        remap = false
    )
    private Block quarkFramedGlassCt$treatPaneBelowAsSame(
        BlockState neighbor,
        BlockState state,
        Direction cullDirection,
        RandomSource random,
        ModelData data,
        RenderType renderType
    ) {
        return groupedBlockOrOriginal(neighbor, state);
    }

    private static Block groupedBlockOrOriginal(BlockState neighbor, BlockState state) {
        if (FramedGlassGroup.containsPane(neighbor.getBlock()) && FramedGlassGroup.containsPane(state.getBlock())) {
            return state.getBlock();
        }
        return neighbor.getBlock();
    }
}
