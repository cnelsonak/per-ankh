// PROTOTYPE (2026-08-20) -- demonstrates the fix proposed in per-ankh's
// scripts/docs/elo-calculator-design.md § "Match Deduplication via
// xml_game_id -- Verified Feasible". Exercises xml_game_id exposure on
// GET /v1/games and GET /v1/games/:id (cloud/src/games.ts). Not part of the
// regular suite until that patch is reviewed and actually adopted.

import { applyD1Migrations, env } from "cloudflare:test";
import { beforeAll, describe, expect, it } from "vitest";
import { expectOk } from "../../helpers/assertions";
import { makeUser } from "../../helpers/builders";
import { seedGame } from "../../helpers/games";
import { request } from "../../helpers/requests";

beforeAll(async () => {
	await applyD1Migrations(env.SHARE_DB, env.TEST_MIGRATIONS);
});

async function setXmlGameId(gameId: string, xmlGameId: string): Promise<void> {
	await env.SHARE_DB.prepare(
		`UPDATE games SET xml_game_id = ? WHERE game_id = ?`,
	)
		.bind(xmlGameId, gameId)
		.run();
}

interface DetailBody {
	xml_game_id: string;
}

interface ListBody {
	games: { game_id: string; xml_game_id: string }[];
}

describe("xml_game_id on GET /v1/games and GET /v1/games/:id (prototype)", () => {
	it("is present on the game-detail response", async () => {
		const owner = await makeUser();
		const gameId = await seedGame(owner, { isPublic: true });
		await setXmlGameId(gameId, "8a378aa9-cfd6-4ce6-b18e-3709c9043d27");

		const body = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${gameId}` }),
		);

		expect(body.xml_game_id).toBe("8a378aa9-cfd6-4ce6-b18e-3709c9043d27");
	});

	it("is present on each row of the game-list response", async () => {
		const owner = await makeUser();
		const gameId = await seedGame(owner, { isPublic: true });
		await setXmlGameId(gameId, "15443b64-8934-4ce4-8bd9-4333b6663280");

		const body = await expectOk<ListBody>(
			await request.get({ path: `/v1/games?user_id=${owner.userId}` }),
		);

		const row = body.games.find((g) => g.game_id === gameId);
		expect(row?.xml_game_id).toBe("15443b64-8934-4ce4-8bd9-4333b6663280");
	});

	it("demonstrates the actual dedup use case: two separate uploads of the same underlying game share xml_game_id", async () => {
		// Two different accounts, each uploading their own perspective's save
		// from the same multiplayer session -- exactly the scenario that
		// currently can't be reconciled via the public API.
		const playerA = await makeUser();
		const playerB = await makeUser();
		const sharedGameId = "b80213c0-d26b-4616-8534-53ab956ca22a";

		const uploadFromA = await seedGame(playerA, { isPublic: true });
		const uploadFromB = await seedGame(playerB, { isPublic: true });
		await setXmlGameId(uploadFromA, sharedGameId);
		await setXmlGameId(uploadFromB, sharedGameId);

		const detailA = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${uploadFromA}` }),
		);
		const detailB = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${uploadFromB}` }),
		);

		expect(detailA.xml_game_id).toBe(sharedGameId);
		expect(detailB.xml_game_id).toBe(sharedGameId);
	});

	it("is distinct across genuinely different games from the same uploader", async () => {
		const uploader = await makeUser();

		const firstGame = await seedGame(uploader, { isPublic: true });
		const secondGame = await seedGame(uploader, { isPublic: true });
		await setXmlGameId(firstGame, "game-one");
		await setXmlGameId(secondGame, "game-two");

		const detail1 = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${firstGame}` }),
		);
		const detail2 = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${secondGame}` }),
		);

		expect(detail1.xml_game_id).not.toBe(detail2.xml_game_id);
	});
});
