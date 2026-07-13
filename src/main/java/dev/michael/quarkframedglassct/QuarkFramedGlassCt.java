package dev.michael.quarkframedglassct;

import com.mojang.logging.LogUtils;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.event.lifecycle.FMLClientSetupEvent;
import org.slf4j.Logger;

@Mod(value = QuarkFramedGlassCt.MOD_ID, dist = Dist.CLIENT)
public final class QuarkFramedGlassCt {
    public static final String MOD_ID = "quark_framed_glass_ct";
    public static final Logger LOGGER = LogUtils.getLogger();

    public QuarkFramedGlassCt(IEventBus modBus) {
        modBus.addListener(this::clientSetup);
    }

    private void clientSetup(FMLClientSetupEvent event) {
        event.enqueueWork(() -> {
            FramedGlassGroup.initialize();
            LOGGER.info(
                "Enabled mosaic CT and cross-color culling for {} Quark framed glass blocks and {} panes",
                FramedGlassGroup.size(),
                FramedGlassGroup.paneSize()
            );
        });
    }
}
