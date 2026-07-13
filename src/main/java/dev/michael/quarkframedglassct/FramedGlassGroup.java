package dev.michael.quarkframedglassct;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.DyeColor;
import net.minecraft.world.level.block.Block;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class FramedGlassGroup {
    private static final Set<Block> BLOCKS = Collections.newSetFromMap(new IdentityHashMap<>());
    private static final Set<Block> PANES = Collections.newSetFromMap(new IdentityHashMap<>());

    private FramedGlassGroup() {
    }

    public static void initialize() {
        BLOCKS.clear();
        PANES.clear();
        add(BLOCKS, "framed_glass");
        add(PANES, "framed_glass_pane");
        for (DyeColor color : DyeColor.values()) {
            add(BLOCKS, color.getName() + "_framed_glass");
            add(PANES, color.getName() + "_framed_glass_pane");
        }
        if (BLOCKS.size() != 17 || PANES.size() != 17) {
            throw new IllegalStateException(
                "Expected 17 Quark framed glass blocks and panes, found " + BLOCKS.size() + " and " + PANES.size()
            );
        }
    }

    private static void add(Set<Block> target, String path) {
        ResourceLocation id = ResourceLocation.fromNamespaceAndPath("quark", path);
        Block block = BuiltInRegistries.BLOCK.get(id);
        if (BuiltInRegistries.BLOCK.getKey(block).equals(BuiltInRegistries.BLOCK.getDefaultKey())) {
            throw new IllegalStateException("Missing required Quark block " + id);
        }
        target.add(block);
    }

    public static boolean contains(Block block) {
        return BLOCKS.contains(block);
    }

    public static boolean containsPane(Block block) {
        return PANES.contains(block);
    }

    public static int size() {
        return BLOCKS.size();
    }

    public static int paneSize() {
        return PANES.size();
    }
}
